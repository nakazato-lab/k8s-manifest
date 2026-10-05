## NFD・NLSRの構成
各 Node に NDN-Router があれば、Unix ソケットを使った通信ができるが、自 Node に NDN-Router がない場合もあるため、ここでは Service を NDN-Router の前段に置き接続を確立できるようにしている。

![nfd-nlsr](docs/images/ndn-router.png)
