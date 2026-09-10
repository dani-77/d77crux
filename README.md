<p align="center">
  <img src="logo.png?v=2" width="128" alt="d77crux logo">
</p>

<h1 align="center">d77crux</h1>

<p align="center">My own collection of CRUX ports — all working; check deps before <code>pkgmk</code>.</p>

---

Download the httpup file and drop it in `/etc/ports/`:

```
wget https://raw.githubusercontent.com/dani-77/d77crux/master/d77crux.httpup
sudo mv d77crux.httpup /etc/ports/
```

Add the collection to `prt-get`:

```
echo 'prtdir /usr/ports/d77crux' | sudo tee -a /etc/prt-get.conf
```

Fetch it, then use any of the ports:

```
sudo ports -u d77crux
```

## Not affiliated with the CRUX project.
