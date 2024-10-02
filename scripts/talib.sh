# for python ta-lib library
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz &&
  tar -xzf ta-lib-0.4.0-src.tar.gz &&
  cd ta-lib/ && ./configure && make && make install
