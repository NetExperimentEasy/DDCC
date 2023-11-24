KERNEL_DIR=/usr/src/kernel-headers-$(shell uname -r)
obj-m += tcp_satcc.o
ccflags-y := -std=gnu99 -Wno-declaration-after-statement

all:
	$(CC) tcp_satcc_user.c -o satcc -static -lhiredis -lpthread
	make -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules
clean:
	rm -f satcc
	make -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean