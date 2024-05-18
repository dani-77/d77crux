ACLOCAL_AMFLAGS = -I m4

SUBDIRS = doc

dist_bin_SCRIPTS = mmaker

nobase_dist_pkgdata_DATA = *.py MenuMaker/*.py Prophet/*.py Prophet/Desktop/*.py Prophet/Legacy/*.py Prophet/Debian/*.py Prophet/Debian/menu/*

install-exec-local :
	echo "#!/usr/bin/env $(PYTHON_BIN)" > $(DESTDIR)/$(bindir)/mmaker
	echo "import sys; sys.path = ['$(pkgdatadir)'] + sys.path" >> $(DESTDIR)/$(bindir)/mmaker
	echo "import MenuMaker.CLI" >> $(DESTDIR)/$(bindir)/mmaker

install-data-local :
	$(PYTHON) -c 'import compileall; compileall.compile_dir(dir="$(DESTDIR)/$(pkgdatadir)", ddir="$(pkgdatadir)")'
