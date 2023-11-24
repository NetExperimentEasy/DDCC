#include <linux/module.h>
#include <net/tcp.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/slab.h>

#include <net/sock.h>
#include <linux/netlink.h>
#include <linux/skbuff.h>

#include <linux/kernel.h> // for sprintf()

#define NETLINK_SATCC 17  // 为什么只能用17？
#define HASH_MAP_SIZE 100
#define USEC_PER_MSEC	1000L
#define MSG_MAX_LEN 512

// delivered calcu scale
#define BW_SCALE 24
#define BW_UNIT (1 << BW_SCALE)
#define div64_long(x, y) div64_s64((x), (y))

#define SCALE 8
#define UNIT (1 << SCALE)

/* min rtt 探索相关参数 */
static const u32 probertt_interval_msec = 10000; // 10s
// static const u32 probertt_interval_msec = 2500; // 2.5s

static const int high_gain  = UNIT * 2885 / 1000 + 1;

struct SATCC_cong
{
	u16 mode : 3,
		exited : 1,
		unused : 12;
	u32 last_sequence;
	u32 sending_throughput; // 采样间隔内评估的发送吞吐
	u64 delivered_rate;  // 交付速率
	u32 last_update_stamp;
	u32 lost_during_interval; // 采样间隔的丢包数
	u32 last_packet_loss;

	u32 last_probertt_stamp;
	u32 start_up_stamp;
	u32 min_rtt_us;

	u32 flow_id; // 唯一标识该流在hash map的位置
};


/* LRU map hash */
typedef struct action_s{
	int cwnd_change;
	int update_flag; // !=0 needed update; 0 don't need update
	// u32 pacing_rate;  // remove support for pacing rate 
}action_t;

static action_t action_map[HASH_MAP_SIZE];
static u32 flow_id_global = 0;
static int pid; // 用户态中转程序的pid，用于netlink通信 // 用户态每次启动程序，要给kernel发一个消息通知一下pid

/*netlink function*/
struct sock *nl_sock = NULL;

static void netlink_recv_msg(struct sk_buff *skb)
{
    struct nlmsghdr *nlh;
	char* const delim = ";";
    char *msg;
	int res;
	u32 flow_id;
	int cwnd_change;

    nlh = (struct nlmsghdr *)skb->data;
    pid = nlh->nlmsg_pid; /* pid of sending process */
    msg = (char *)nlmsg_data(nlh);

	// todo: read flow_id from msg
	char *str, *cur = msg;
	str = strsep(&cur, delim);
	res = kstrtoint(str, 10, &flow_id);
	if (res < 0)
      printk(KERN_INFO "netlink_satcc: Error while converte flow_id string to int\n");

	str = strsep(&cur, delim);
	res = kstrtoint(str, 10, &cwnd_change);
	if (res < 0)
      printk(KERN_INFO "netlink_satcc: Error while converte cwnd string to int\n");
	
	action_t action = {cwnd_change, 1};  // change flag to need_update state
	action_map[flow_id] = action;

	// printk(KERN_INFO "netlink_satcc: flow_id: %d, cwnd: %u, pacing_rate: %d\n", flow_id, cwnd, pacing_rate);
}

static void netlink_send_msg(char *msg)
{
	struct sk_buff *skb_out;
	struct nlmsghdr *nlh;
	int msg_size;
	int res;

	// 计算msg_size
	msg_size = strlen(msg);

	// create reply
    skb_out = nlmsg_new(msg_size, 0);
	if (!skb_out) {
      printk(KERN_ERR "netlink_satcc: Failed to allocate new skb\n");
      return;
    }

	// put received message into reply
    nlh = nlmsg_put(skb_out, 0, 0, NLMSG_DONE, msg_size, 0);
    NETLINK_CB(skb_out).dst_group = 0; /* not in mcast group */
    strncpy(nlmsg_data(nlh), msg, msg_size);

    // printk(KERN_INFO "netlink_satcc: Send %s\n", msg);

    res = nlmsg_unicast(nl_sock, skb_out, pid);
    if (res < 0)
      printk(KERN_INFO "netlink_satcc: Error while sending skb to user\n");
	// 用户态 必须接收数据，否则这里就报错了
}

static void calc_lost_during_interval(struct sock *sk)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct SATCC_cong *sc = inet_csk_ca(sk);
	u32 training_interval_msec;
	// training_interval_msec = 2 * (sc->min_rtt_us>>10); //2RTT
	training_interval_msec = (sc->min_rtt_us>>10)<=100 ? 2 * (sc->min_rtt_us>>10) : (sc->min_rtt_us>>10)+100; // 针对高延迟场景的采样周期优化
	
	sc->lost_during_interval = (tp->lost - sc->last_packet_loss) * training_interval_msec / jiffies_to_msecs(tcp_jiffies32 - sc->last_update_stamp);
	sc->last_packet_loss = tp->lost;
}

static void calc_throughput(struct sock *sk)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct SATCC_cong *sc = inet_csk_ca(sk);
	u32 segout_for_interval;

	segout_for_interval = (tp->segs_out - sc->last_sequence) * tp->mss_cache;

	sc->sending_throughput = segout_for_interval * 8 / jiffies_to_msecs(tcp_jiffies32 - sc->last_update_stamp);

	sc->last_sequence = tp->segs_out;
}


static void update_state(struct sock *sk, const struct rate_sample *rs)
{	
	struct tcp_sock *tp = tcp_sk(sk);
	struct SATCC_cong *sc = inet_csk_ca(sk);
	char msg[MSG_MAX_LEN];

	sc->delivered_rate = div64_long((u64)rs->delivered * BW_UNIT, rs->interval_us);

	/*
	sc->delivered_rate; // >> 10 , Mbps
	sc->sending_throughput;
	sc->min_rtt_us; // >> 10;
	rs->rtt_us;
	rs->losses；
	rs->prior_in_flight；
	*/
	sprintf(msg, "%u;%llu;%u;%u;%lu;%d;%u;%u", sc->flow_id, sc->delivered_rate, sc->sending_throughput, sc->min_rtt_us, rs->rtt_us, rs->losses, rs->prior_in_flight, tp->snd_cwnd);
	netlink_send_msg(msg);
}

static u64 rate_bytes_per_sec(struct sock *sk, u64 rate, int gain)
{
	unsigned int mss = tcp_sk(sk)->mss_cache;

	rate *= mss;
	rate *= gain;
	rate >>= SCALE;
	rate *= USEC_PER_SEC / 100 * (100 - 1);
	return rate >> BW_SCALE;
}

static unsigned long bw_to_pacing_rate(struct sock *sk, u32 bw, int gain)
{
	u64 rate = bw;

	rate = rate_bytes_per_sec(sk, rate, gain);
	rate = min_t(u64, rate, sk->sk_max_pacing_rate);
	return rate;
}

static void training(struct sock *sk, const struct rate_sample *rs)
{	
	struct tcp_sock *tp = tcp_sk(sk);
	struct SATCC_cong *sc = inet_csk_ca(sk);
	u32 training_interval_msec;
	u32 training_timer_expired;
	action_t action;
	u64 bw;
	u32 rtt_us;
	int cwnd;

	training_interval_msec = 2 * (sc->min_rtt_us>>10); //2RTT

	training_timer_expired = after(tcp_jiffies32, sc->last_update_stamp + msecs_to_jiffies(training_interval_msec));

	// 必须加这个判断，否则后续计算会溢出
	if (rs->delivered < 0 || rs->interval_us <= 0)
		return; /* Not a valid observation */

	if (training_timer_expired)
	{	
		calc_throughput(sk);
		calc_lost_during_interval(sk);
		// update and send message to user space code
		update_state(sk, rs);
		sc->last_update_stamp = tcp_jiffies32;
	}

	// read action from global LRU hash map
	action = action_map[sc->flow_id];
	// if (action.cwnd!=0 && action.pacing_rate!=0) {
	// 	tp->snd_cwnd = action.cwnd;
	// 	sk->sk_pacing_rate = action.pacing_rate;
	// }

	if (action.update_flag != 0) {
		cwnd = (int)(tp->snd_cwnd) + action.cwnd_change;
		if (cwnd < 4)
			cwnd = 4;
		// printk(KERN_INFO "cwnd_change: %d, update flag: %d,netlink_satcc: change cwnd from %u,(%d) to %u,(%d)\n",action.cwnd_change, action.update_flag, tp->snd_cwnd, (int)(tp->snd_cwnd), (u32)(cwnd), cwnd);
		tp->snd_cwnd = (u32)(cwnd);
		

		if (tp->srtt_us) {		/* any RTT sample yet? */
			rtt_us = max(tp->srtt_us >> 3, 1U);
		} else {			 /* no RTT sample yet */
			rtt_us = USEC_PER_MSEC;	 /* use nominal default RTT */
		}
		bw = (u64)(tp->snd_cwnd) * BW_UNIT;
		do_div(bw, rtt_us);
		sk->sk_pacing_rate = bw_to_pacing_rate(sk, bw, high_gain);

		action_map[sc->flow_id].update_flag = 0;
	}

}


static void reset_cwnd(struct sock *sk, const struct rate_sample *rs){
}

static u32 SATCC_cong_undo_cwnd(struct sock *sk)
{
	struct tcp_sock *tp = tcp_sk(sk);
	return max(tp->snd_cwnd, tp->prior_cwnd);
}

static u32 SATCC_cong_ssthresh(struct sock *sk)
{
	return TCP_INFINITE_SSTHRESH; /* does not use ssthresh */
}

static void SATCC_cong_main(struct sock *sk, const struct rate_sample *rs)
{	
	// reset_cwnd(sk, rs);
	training(sk, rs);
}


static void init_SATCC_cong(struct sock *sk)
{	
	struct SATCC_cong *sc = inet_csk_ca(sk);
	struct tcp_sock *tp = tcp_sk(sk);

	sc->last_sequence = 0;
	sc->sending_throughput = 0;
	
	sc->delivered_rate = 0;
    sc->last_update_stamp = tcp_jiffies32;
    sc->last_packet_loss = 0;
    sc->lost_during_interval = 0;

    sc->last_probertt_stamp = tcp_jiffies32;
    sc->start_up_stamp = tcp_jiffies32;
    sc->min_rtt_us = tcp_min_rtt(tp);

	sc->flow_id = flow_id_global;
	flow_id_global += 1;
	if(flow_id_global > HASH_MAP_SIZE)
	{
		flow_id_global = 0;
	}
}

static void release_SATCC_cong(struct sock *sk)
{	
	struct SATCC_cong *sc = inet_csk_ca(sk);

	action_t action = {
		.cwnd_change = 0,
		.update_flag = 0,
	};
	action_map[sc->flow_id] = action;
}

struct tcp_congestion_ops satcc_cong = {
	.flags = TCP_CONG_NON_RESTRICTED,
	.init = init_SATCC_cong,
	.release = release_SATCC_cong,
	.name = "satcc",
	.owner = THIS_MODULE,
	.ssthresh = SATCC_cong_ssthresh,
	.cong_control = SATCC_cong_main,
	.undo_cwnd = SATCC_cong_undo_cwnd,
};

// references https://github1s.com/mwarning/netlink-examples/blob/master/unicast_example/netlink_test.c
static int __init SATCC_cong_init(void)
{	
	printk(KERN_INFO "tcp_satcc and netlink_satcc: Init module\n");

	memset(&action_map, 0, sizeof(action_map));

	struct netlink_kernel_cfg cfg = {
		.input = netlink_recv_msg,
	};

	nl_sock = netlink_kernel_create(&init_net, NETLINK_SATCC, &cfg);
	if (!nl_sock) {
		printk(KERN_ALERT "netlink_satcc: Error creating socket.\n");
		return -10;
	}

	BUILD_BUG_ON(sizeof(struct SATCC_cong) > ICSK_CA_PRIV_SIZE);
	return tcp_register_congestion_control(&satcc_cong);
}

static void __exit SATCC_cong_exit(void)
{
	tcp_unregister_congestion_control(&satcc_cong);

	netlink_kernel_release(nl_sock);
}

module_init(SATCC_cong_init);
module_exit(SATCC_cong_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Seclee");
MODULE_DESCRIPTION("SATCC: A Congestion Control Algorithm for Dynamic Satellite Networks");