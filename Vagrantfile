Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/bionic64"
  config.vm.network "forwarded_port", guest: 5500, host: 5500, host_ip: "127.0.0.1"
  config.vm.network "forwarded_port", guest: 3306, host: 3306, host_ip: "127.0.0.1"
  config.vm.provision "shell", inline: <<-SHELL
    echo "Starting provision"
    echo "Adding keys and repositories" 
    apt-key adv --recv-keys --keyserver hkp://keyserver.ubuntu.com:80 0xF1656F24C74CD1D8
    add-apt-repository 'deb [arch=amd64,arm64,ppc64el] https://mirrors.shu.edu.cn/mariadb/repo/10.3/ubuntu bionic main'
    apt-get update
    echo "Inserting default root's password for mariadb"
    echo "mariadb-server-10.3 mysql-server/root_password_again password toor" | debconf-set-selections
    echo "mariadb-server-10.3 mysql-server/root_password password toor" | debconf-set-selections
    echo "Installing depenencies"
    apt-get install -y git python-pip make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev mariadb-server default-libmysqlclient-dev
    echo "Creating user in mariadb"
    echo "CREATE USER 'test'@'localhost' IDENTIFIED BY 'test123'; GRANT ALL PRIVILEGES ON *.* TO 'test'@'localhost'; FLUSH PRIVILEGES; CREATE DATABASE nyaav2 DEFAULT CHARACTER SET utf8 COLLATE utf8_bin;" | mysql -u root -ptoor
    echo "Getting pyenv"
    git clone https://github.com/yyuu/pyenv.git ~/.pyenv
    git clone https://github.com/pyenv/pyenv-virtualenv.git ~/.pyenv/plugins/pyenv-virtualenv
    echo "Inserting environmental variables"
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
    echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc
    echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
    # Ugly hack; source ~/.bashrc, . ~/.bashrc, setting two provisioners with 'reset: "true"' not working
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    eval "$(pyenv virtualenv-init -)"
    echo "Installing virtual environment"
    pyenv install 3.6.1
    pyenv virtualenv 3.6.1 nyaa
    pyenv activate nyaa
    cd /vagrant
    echo "Istalling nyaa depenencies"
    pip install -r requirements.txt
    echo "Copying config.py"
    cp config.example.py config.py
    echo "Creating database"
    python db_create.py
    ./db_migrate.py stamp head
  SHELL
end