PACKAGES=xcomposite xfixes xdamage xrender
LIBS=`pkg-config --libs ${PACKAGES}` -lm
INCS=`pkg-config --cflags ${PACKAGES}`
CFLAGS = -Wall

.c.o:
	$(CC) $(CFLAGS) $(INCS) -c $*.c

OBJS=transSet.o dsimple.o

transset-df: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LIBS)

$(OBJS): dsimple.h

install:
	cp transset-df /usr/bin

clean:
	rm -f $(OBJS) transset-df
