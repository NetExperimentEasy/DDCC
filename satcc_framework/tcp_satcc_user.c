#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#define NETLINK_SATCC 17

#include <sys/socket.h>
#include <linux/netlink.h>

#include <hiredis/hiredis.h>
#include "pthread.h"

#include <signal.h>

#define MAX_PAYLOAD 1024  /* maximum payload size*/
#define MSG_MAX_LEN 512

/* netlink module */
typedef struct netlink_cfg_s{
  int sock_fd;
  struct sockaddr_nl src_addr;
  struct sockaddr_nl dest_addr;
}netlink_cfg_t;

int init_netlink(netlink_cfg_t *cfg)
{
  cfg->sock_fd = socket(PF_NETLINK, SOCK_RAW, NETLINK_SATCC);
  if (cfg->sock_fd < 0) {
    printf("socket: %s\n", strerror(errno));
    return -1;
  }

  cfg->src_addr.nl_family = AF_NETLINK;
  cfg->src_addr.nl_pid = getpid();  /* self pid */
  cfg->src_addr.nl_groups = 0;  /* not in mcast groups */

  bind(cfg->sock_fd, (struct sockaddr*)&cfg->src_addr, sizeof(cfg->src_addr));

  cfg->dest_addr.nl_family = AF_NETLINK;
  cfg->dest_addr.nl_pid = 0;   /* For Linux Kernel */
  cfg->dest_addr.nl_groups = 0; /* unicast */

  printf("init netlink: successed! sock_fd: %d\n", cfg->sock_fd);

  return 1;
}

void netlink_recv_msg(netlink_cfg_t *cfg, char *recv_msg)
{
  struct nlmsghdr *nlh;
  struct msghdr msg;
  struct iovec iov;
  int ret;
  int msg_size;
  
  /* Read message from kernel */
  nlh = (struct nlmsghdr *)malloc(NLMSG_SPACE(MAX_PAYLOAD));
  nlh->nlmsg_len = NLMSG_SPACE(MAX_PAYLOAD);
  nlh->nlmsg_pid = getpid();  /* self pid */
  nlh->nlmsg_flags = 0;

  memset(&iov, 0, sizeof(iov));
  iov.iov_base = (void *)nlh;
  iov.iov_len = nlh->nlmsg_len;

  memset(&msg, 0, sizeof(msg));
  msg.msg_name = (void *)&cfg->dest_addr;
  msg.msg_namelen = sizeof(cfg->dest_addr);
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;

  memset(nlh, 0, NLMSG_SPACE(MAX_PAYLOAD));

  ret = recvmsg(cfg->sock_fd, &msg, 0);
  if (ret < 0) {
    printf("recvmsg: %s\n", strerror(errno));
    close(cfg->sock_fd);
  }
  // printf("Received from kernel: %s\n", NLMSG_DATA(nlh));

  msg_size = strlen(NLMSG_DATA(nlh));
  strncpy(recv_msg, NLMSG_DATA(nlh), msg_size);
}

void netlink_send_msg(netlink_cfg_t *cfg, char *msg_payload)
{
  struct nlmsghdr *nlh;
  struct msghdr msg;
  struct iovec iov;
  int ret;

  nlh = (struct nlmsghdr *)malloc(NLMSG_SPACE(MAX_PAYLOAD));
  nlh->nlmsg_len = NLMSG_SPACE(MAX_PAYLOAD);
  nlh->nlmsg_pid = getpid();  /* self pid */
  nlh->nlmsg_flags = 0;

  memset(&iov, 0, sizeof(iov));
  iov.iov_base = (void *)nlh;
  iov.iov_len = nlh->nlmsg_len;

  memset(&msg, 0, sizeof(msg));
  msg.msg_name = (void *)&cfg->dest_addr;
  msg.msg_namelen = sizeof(cfg->dest_addr);
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;

  /* Fill in the netlink message payload */
  strcpy(NLMSG_DATA(nlh), msg_payload);

  // printf("Send to kernel: %s\n", msg_payload);

  ret = sendmsg(cfg->sock_fd, &msg, 0);
  if (ret < 0) {
    printf("sendmsg: %s\n", strerror(errno));
    close(cfg->sock_fd);
  }
}


/* redis module */
typedef struct redis_cfg_s{
  char *redis_host;
  uint32_t redis_port;
  redisContext *listener;
  redisContext *publisher;
  redisReply *reply;
}redis_cfg_t;

typedef struct action_s{
  int flow_id;
  uint32_t cwnd;
  // uint32_t pacing_rate;
}action_t;

typedef struct state_s{
  int flow_id;
  uint64_t delivered_rate;
  uint32_t sending_throughput;
  uint32_t min_rtt_us;
  uint32_t rtt_us;
  int losses;
  uint32_t prior_in_flight;
  uint32_t snd_cwnd;
  // uint32_t pacing_rate;
  char *str; // 存放序列后的字符串，不含flow_id
}state_t;

int init_redis(redis_cfg_t *cfg)
{	
	cfg->listener = redisConnect(cfg->redis_host, cfg->redis_port);
	cfg->publisher = redisConnect(cfg->redis_host, cfg->redis_port);

	if (!cfg->listener || !cfg->publisher)
	{
		printf("redisConnect error\n");
    return -1;
	}
	else if (cfg->listener->err)
	{
		printf("redis connection error:%s\n", cfg->listener->errstr);
		redisFree(cfg->listener);
    return -1;
	}
	else if (cfg->publisher->err)
	{
		printf("redis connection error:%s\n", cfg->publisher->errstr);
		redisFree(cfg->publisher);
    return -1;
  }
  printf("init redis client: successed!\n");
	return 1; 
}

void subscribe(redis_cfg_t *cfg)
{
	if ((cfg->reply = redisCommand(cfg->listener, "PSUBSCRIBE rlccaction_*")) == NULL)
	{
		printf("Failed to PSUBSCRIBE\n");
		redisFree(cfg->listener);
	}
	else
	{
		freeReplyObject(cfg->reply);
	}
  printf("PSUBSCRIBE rlccaction_* succeed!\n");
	return;
}

/* get action from redis */
int get_result_from_redis_reply(redis_cfg_t *cfg, action_t *act)
{
  int redis_err = 0;
  void *reply = cfg->reply;
  char *tmp_str;
  char channel[10];

  if ((redis_err = redisGetReply(cfg->listener, &reply)) == REDIS_OK)
  { 
    /*
    redisReply *r = reply;
    if (r->type == REDIS_REPLY_ARRAY) {
        for (int j = 0; j < r->elements; j++) {
            printf("%u) %s\n", j, r->element[j]->str);
        }
    }
    // 0) pmessage
    // 1) rlccaction_*
    // 2) rlccaction_1
    // 3) test
    */

    redisReply *r = reply;
    if (r->type ==  REDIS_REPLY_ARRAY)
    {
      // get flag, cwnd
      tmp_str = r->element[2]->str;
      memcpy(channel, tmp_str+11, strlen(tmp_str)-11); //  rlccaction_1 截取数字部分
      sscanf(channel, "%d", &act->flow_id);
      // printf("channel: %s, msg: %s\n", channel, r->element[3]->str);
      sscanf(r->element[3]->str, "%d", &act->cwnd);
      // printf("action cwnd: %d\n", act->cwnd);
      freeReplyObject(reply);
      return 1;
    }
    freeReplyObject(reply);
  }
	return -1;
}

void push_state(redis_cfg_t *cfg, state_t *state)
{
	/* publish state */
	redisReply *reply;

	reply = redisCommand(cfg->publisher, "PUBLISH rlccstate_%d %s", state->flow_id, state->str);

	if (reply != NULL)
		freeReplyObject(reply);

	return;
}

/* thread function */
typedef struct thparam_s {
  redis_cfg_t *redis_cfg;
	netlink_cfg_t *netlink_cfg;
}thparam_t;

// 从外部向内核的action消息传递
void * get_action_from_redis_to_kernel(void *arg)
{
  thparam_t parm = *(thparam_t *)arg;
  redis_cfg_t *rcfg = parm.redis_cfg;
  netlink_cfg_t *ncfg = parm.netlink_cfg;

	int ret;
  action_t action;
  memset(&action, 0, sizeof(action));
  char *msg = (char *)malloc(MSG_MAX_LEN);

	while (1)
	{
    ret = get_result_from_redis_reply(rcfg, &action);
    if(ret > 0)
    {
      // printf("action flow_id: %d, cwnd: %d\n", action.flow_id, action.cwnd);
      sprintf(msg, "%d;%d", action.flow_id, action.cwnd);
      netlink_send_msg(ncfg, msg);
    }
	}
	return 0;
}

// 从外部向内核的action消息传递
void * get_state_from_kernel_to_redis(void *argc)
{
  thparam_t parm = *(thparam_t *)argc;
  redis_cfg_t *rcfg = parm.redis_cfg;
  netlink_cfg_t *ncfg = parm.netlink_cfg;

	int redis_err = 0;
  state_t state;
  char *send_msg = (char *)malloc(MSG_MAX_LEN);
  memset(&state, 0, sizeof(state));
  char *msg = (char *)malloc(MSG_MAX_LEN);
	// xqc_rlcc_t *rlcc = (xqc_rlcc_t *)arg;

	while (1)
	{
		netlink_recv_msg(ncfg, msg);
    // printf("%s\n", msg);
    // 解析数据
    sscanf(msg, "%d;%lu;%u;%u;%u;%d;%u;%u", &state.flow_id, &state.delivered_rate, &state.sending_throughput, &state.min_rtt_us, &state.rtt_us, &state.losses, &state.prior_in_flight, &state.snd_cwnd);
    // printf("%d,%lu,%u,%u,%u\n",  state.flow_id, state.delivered_rate, state.sending_throughput, state.min_rtt_us, state.rtt_us);
    // 重新序列化数据
    sprintf(send_msg, "%lu;%u;%u;%u;%d;%u;%u", state.delivered_rate, state.sending_throughput, state.min_rtt_us, state.rtt_us, state.losses, state.prior_in_flight, state.snd_cwnd);
    state.str = send_msg;
    // printf("%s\n", state.str);
    push_state(rcfg, &state);
	}
	return 0;
}


int main(int argc, char **argv)
{
  int ret;
  char *msg_payload;
  char *recv_msg;

  printf("satcc: started! press ctrl_c to stop\n");

  /* start netlink */
  netlink_cfg_t netlink_cfg;
  memset(&netlink_cfg, 0, sizeof(netlink_cfg));

  recv_msg = (char *)malloc(MSG_MAX_LEN);

  ret = init_netlink(&netlink_cfg);  
  if(ret < 0){
    printf("satcc_user: error while init netlink\n");
    return ret;
  }

  msg_payload = "0;0;0"; // 启动时必须先发一次初始化消息，告知内核用户态程序的pid用于通信
  netlink_send_msg(&netlink_cfg, msg_payload);
  
  /* start redis */
  redis_cfg_t redis_cfg;
  memset(&redis_cfg, 0, sizeof(redis_cfg));
  redis_cfg.redis_host = "127.0.0.1";
  redis_cfg.redis_port = 6379;
  redis_cfg.reply = NULL;

  ret = init_redis(&redis_cfg);
  if (ret == -1){
    printf("init redis client error!\n");
    return 1;
  }
  subscribe(&redis_cfg);

  /* main logic*/
  pthread_t tid_in, tid_out;

  thparam_t parm = {&redis_cfg, &netlink_cfg};

  ret = pthread_create(&tid_in, NULL, get_action_from_redis_to_kernel, &parm);
  if(ret == -1){
      printf("Create pthread error!\n");
      return 1;
  }
  printf("Create pthread succeed!: get_action_from_redis_to_kernel()\n");
  ret = pthread_create(&tid_out, NULL, get_state_from_kernel_to_redis, &parm);	
  if(ret == -1){
      printf("Create pthread error!\n");
      return 1;
  }
  printf("Create pthread succeed!: get_state_from_kernel_to_redis()\n");

  /* 内嵌信号处理，资源回收 */
  void sigint_handler(int sig){
    if(sig == SIGINT){
        // ctrl+c退出时执行的代码
        printf("satcc: closing\n");
        /* Close Netlink Socket */
        printf("satcc: canceling all threads\n");
        pthread_cancel(tid_in);
        pthread_cancel(tid_out);
        printf("satcc: clean all resources\n");
        close(netlink_cfg.sock_fd);
        /* Close redis client */
        redisFree(redis_cfg.listener);
        redisFree(redis_cfg.publisher);
        printf("satcc: closed!\n"); 
      }
  }
  signal(SIGINT, sigint_handler);

  pthread_join(tid_in, NULL);  //阻塞主线程，直到进程结束，
  pthread_join(tid_out, NULL);

  return 0;
}
