# docker build -t $IMAGE_NAME .
# docker run --volume=workspace:/workspace -p $SSH_PORT:22 -p $JUPYTER_PORT:8888 --restart=always -t -d $IMAGE_NAME
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV LC_ALL=C.UTF-8

# essential
RUN apt update && \
    apt install -y build-essential openssh-server curl git wget gh ninja-build gettext cmake unzip

# zsh
RUN apt install -y zsh
RUN chsh -s /bin/zsh
RUN wget https://github.com/robbyrussell/oh-my-zsh/raw/master/tools/install.sh -O - | zsh

RUN git clone https://github.com/zsh-users/zsh-autosuggestions $HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions
RUN git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting

# mise
RUN curl https://mise.run | sh && \
    echo 'eval "$(mise activate zsh)"' >> $HOME/.zshrc
ENV PATH="/root/.local/share/mise/shims:/root/.local/bin:$PATH"

# mise - golang, node, python
# - DAP delve needs global golang
# - lazyvim needs nodejs
RUN apt install -y zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev uuid-dev lzma-dev liblzma-dev checkinstall libncursesw5-dev libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev && \
    mise use -g golang@1.23.1 node@22.9.0 python@3.11.10

# zoxide
RUN curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh && \
    echo 'eval "$(/root/.local/bin/zoxide init zsh)"' >> $HOME/.zshrc

# pipx
RUN apt install -y pipx && \
    pipx ensurepath

# poetry
RUN pipx install poetry && \
    echo "export PATH=$PATH:/root/.local/bin" >> $HOME/.zshrc && \
    /root/.local/bin/poetry config virtualenvs.create false

# zsh plugins
RUN perl -pi -w -e 's/plugins=.*/plugins=(git ssh-agent zsh-autosuggestions zsh-syntax-highlighting mise)/g;' $HOME/.zshrc

# lazyvim
RUN git clone https://github.com/neovim/neovim --branch stable /tmp/neovim && \
    cd /tmp/neovim && \
    make CMAKE_BUILD_TYPE=RelWithDebInfo && \
    make install

# configs
RUN git clone https://github.com/hongzio/hongzio.github.io.git $HOME/.hongzio.github.io

RUN apt install -y lua5.4 liblua5.4-dev luarocks fd-find ripgrep && \
    mkdir -p $HOME/.config && \
    ln -s $HOME/.hongzio.github.io/lazyvim $HOME/.config/lazyvim && \
    echo "export NVIM_APPNAME=lazyvim" >> $HOME/.zshrc && \
    LAZYGIT_VERSION=$(curl -s "https://api.github.com/repos/jesseduffield/lazygit/releases/latest" | grep -Po '"tag_name": "v\K[^"]*') && \
    curl -Lo lazygit.tar.gz "https://github.com/jesseduffield/lazygit/releases/latest/download/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz" && \
    tar xf lazygit.tar.gz lazygit && \
    install lazygit /usr/local/bin && \
    npm install -g tree-sitter-cli && \
    echo "alias vi=nvim\nalias vim=nvim\n\n" >> $HOME/.zshrc

# tmux
RUN apt install -y tmux && \
    git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm && \
    ln -s $HOME/.hongzio.github.io/tmux.conf $HOME/.tmux.conf

# git
RUN cp $HOME/.hongzio.github.io/gitconfig $HOME/.gitconfig

# misc
RUN apt install -y btop

# clean up
RUN apt-get clean && \
    apt-get autoclean && \
    apt-get autoremove -y && \
    rm -rf /var/lib/cache/* && \
    rm -rf /var/lib/log/*

RUN echo 'export EDITOR=nvim\n' >> $HOME/.zshrc

RUN echo 'root:hongzio' | chpasswd && \
    mkdir /var/run/sshd && \
    echo 'PermitRootLogin yes' > /etc/ssh/sshd_config.d/root.conf && \
    echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config.d/root.conf 
CMD ["/usr/sbin/sshd", "-D"]
