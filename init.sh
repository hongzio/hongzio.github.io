#!/usr/bin/env bash

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

CHECKPOINT_FILE="$TMPDIR/checkpoint"

# Function to check if a step has been completed
check_step() {
  grep -q "$1" "$CHECKPOINT_FILE" 2>/dev/null
}

# Function to mark a step as completed
mark_step() {
  echo "$1" >>"$CHECKPOINT_FILE"
}

if ! check_step "xcode-select"; then
  if ! xcode-select -p &>/dev/null; then
    echo -e "${GREEN}Command line tools are not installed. Installing...${NC}"
    xcode-select --install
    echo -e "${GREEN}After installing, run this script again.${NC}"
    echo -e "${GREEN}Run this script with
      ${RED}/bin/bash -c \"\$(curl hongzio.com/init.sh)\"${NC}"
    exit 0
  fi
  mark_step "xcode-select"
else
  echo -e "${GREEN}Skipping xcode-select installation, already completed.${NC}"
fi

if ! check_step "homebrew"; then
  if ! command -v brew &>/dev/null; then
    echo -e "${GREEN}Homebrew is not installed. Installing...${NC}"
    echo -e "${RED}What version of Homebrew do you want to install? (${GREEN}local${RED}/${GREEN}global${RED})${NC}"
    read -r version
    if [[ $version == "local" ]]; then
      cd && mkdir .homebrew && curl -L https://github.com/Homebrew/brew/tarball/master | tar xz --strip 1 -C .homebrew || {
        echo -e "${RED}Failed to install homebrew${NC}"
        exit 1
      }
      echo >>$HOME/.zprofile
      echo 'export PATH=$HOME/.homebrew/bin:$PATH' >>$HOME/.zprofile
      export PATH=$HOME/.homebrew/bin:$PATH
    elif [[ $version == "global" ]]; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
        echo -e "${RED}Failed to install homebrew${NC}"
        exit 1
      }
      echo >>$HOME/.zprofile
      echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >>$HOME/.zprofile
      eval "$(/opt/homebrew/bin/brew shellenv)"
    else
      echo -e "${RED}Invalid option. Please choose local or global${NC}"
      exit 1
    fi
  else
    echo -e "${GREEN}Homebrew is already installed.${NC}"
  fi
  mark_step "homebrew"
else
  echo -e "${GREEN}Skipping Homebrew installation, already completed.${NC}"
fi

BREW_PATH=$(command -v brew)

if ! check_step "karabiner-elements"; then
  $BREW_PATH install karabiner-elements || {
    echo -e "${RED}Failed to install karabiner-elements${NC}"
    exit 1
  }
  echo -e "${RED}Karabiner-Elements is installed. Please set up the configuration manually and System Preferences${NC}"
  mark_step "karabiner-elements"
else
  echo -e "${GREEN}Skipping karabiner-elements installation, already completed.${NC}"
fi

if ! check_step "git"; then
  echo -e "\n${RED}Installing Git...${NC}"
  $BREW_PATH install git || {
    echo -e "${RED}Failed to install git${NC}"
    exit 1
  }
  git config --global user.name hongzio || {
    echo -e "${RED}Failed to set git user name${NC}"
    exit 1
  }
  git config --global user.email hongzio@user.noreply.github.com || {
    echo -e "${RED}Failed to set git user email${NC}"
    exit 1
  }
  git config --global core.excludesFile $HOME/.gitignore || {
    echo -e "${RED}Failed to set gitignore${NC}"
    exit 1
  }
  git config --global init.defaultBranch main || {
    echo -e "${RED}Failed to set default branch${NC}"
    exit 1
  }
  # git config --global url."git@github.com:".insteadOf "https://github.com/" || {
  #   echo -e "${RED}Failed to set git url${NC}"
  #   exit 1
  # }
  echo ".tool-versions
  .direnv
  .envrc
  .idea
  .DS_Store" >$HOME/.gitignore
  mark_step "git"
else
  echo -e "${GREEN}Skipping Git installation, already completed.${NC}"
fi

if ! check_step "zsh"; then
  echo -e "\n${RED}Installing Zsh...${NC}"
  $BREW_PATH install zsh zsh-completions || {
    echo -e "${RED}Failed to install zsh${NC}"
    exit 1
  }
  RUNZSH=no sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" || {
    echo -e "${RED}Failed to install oh-my-zsh${NC}"
    exit 1
  }
  git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting || {
    echo -e "${RED}Failed to install zsh-syntax-highlighting${NC}"
    exit 1
  }
  git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions || {
    echo -e "${RED}Failed to install zsh-autosuggestions${NC}"
    exit 1
  }
  git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k || {
    echo -e "${RED}Failed to install powerlevel10k${NC}"
    exit 1
  }
  mark_step "zsh"
else
  echo -e "${GREEN}Skipping Zsh installation, already completed.${NC}"
fi

if ! check_step "zsh_setup"; then
  echo -e "${RED}Setting up Zsh...${NC}"
  sed -i '' 's/ZSH_THEME="robbyrussell"/ZSH_THEME="powerlevel10k\/powerlevel10k"/' $HOME/.zshrc
  sed -i '' 's/plugins=(git)/plugins=(git zsh-syntax-highlighting zsh-autosuggestions)/' $HOME/.zshrc

  echo "

  # zsh-completions
  if type brew &>/dev/null; then
    FPATH=\$(brew --prefix)/share/zsh-completions:\$FPATH
    autoload -Uz compinit
    compinit
  fi
  " >>$HOME/.zshrc
  mark_step "zsh_setup"
else
  echo -e "${GREEN}Skipping Zsh setup, already completed.${NC}"
fi

if ! check_step "brew_install_iterm2"; then
  echo -e "${RED}Installing iTerm2...${NC}"
  $BREW_PATH install iterm2 || {
    echo -e "${RED}Failed to install iTerm2${NC}"
    exit 1
  }
  mark_step "brew_install_iterm2"
else
  echo -e "${GREEN}Skipping iTerm2 installation, already completed.${NC}"
fi

if ! check_step "brew_install_fzf"; then
  echo -e "${RED}Installing fzf...${NC}"
  $BREW_PATH install fzf || {
    echo -e "${RED}Failed to install fzf${NC}"
    exit 1
  }
  echo "source <(fzf --zsh)" >>$HOME/.zshrc
  mark_step "brew_install_fzf"
else
  echo -e "${GREEN}Skipping fzf installation, already completed.${NC}"
fi

if ! check_step "brew_install_zoxide"; then
  echo -e "${RED}Installing zoxide...${NC}"
  $BREW_PATH install zoxide || {
    echo -e "${RED}Failed to install zoxide${NC}"
    exit 1
  }
  echo "eval \"\$(zoxide init zsh)\"" >>$HOME/.zshrc
  mark_step "brew_install_zoxide"
else
  echo -e "${GREEN}Skipping zoxide installation, already completed.${NC}"
fi

if ! check_step "brew_install_asdf"; then
  echo -e "${RED}Installing asdf...${NC}"
  $BREW_PATH install xz || {
    echo -e "${RED}Failed to install xz${NC}"
    exit 1
  }
  $BREW_PATH install asdf || {
    echo -e "${RED}Failed to install asdf${NC}"
    exit 1
  }
  echo -e "export PATH=\"\${ASDF_DATA_DIR:-\$HOME/.asdf}/shims:\$PATH\"" >> $HOME/.zshrc
  mark_step "brew_install_asdf"
else
  echo -e "${GREEN}Skipping asdf installation, already completed.${NC}"
fi

if ! check_step "brew_install_direnv"; then
  echo -e "${RED}Installing direnv...${NC}"
  $BREW_PATH install direnv || {
    echo -e "${RED}Failed to install direnv${NC}"
    exit 1
  }
  echo "eval \"\$(direnv hook zsh)\"" >>$HOME/.zshrc
  mark_step "brew_install_direnv"
else
  echo -e "${GREEN}Skipping direnv installation, already completed.${NC}"
fi

if ! check_step "brew_install_tmux"; then
  echo -e "${RED}Installing Tmux...${NC}"
  $BREW_PATH install tmux || {
    echo -e "${RED}Failed to install tmux${NC}"
    exit 1
  }
  git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm || {
    echo -e "${RED}Failed to install tpm${NC}"
    exit 1
  }
  ln -s -f $HOME/.hongzio.github.io/tmux.conf $HOME/.tmux.conf || {
    echo -e "${RED}Failed to link tmux.conf${NC}"
    exit 1
  }
  mark_step "brew_install_tmux"
else
  echo -e "${GREEN}Skipping Tmux installation, already completed.${NC}"
fi

if ! check_step "brew_install_neovim"; then
  echo -e "${RED}Installing Neovim...${NC}"
  $BREW_PATH install fd lazygit ripgrep || {
    echo -e "${RED}Failed to install fd, lazygit, ripgrep${NC}"
    exit 1
  }
  $BREW_PATH install neovim || {
    echo -e "${RED}Failed to install neovim${NC}"
    exit 1
  }
  echo "

  # neovim
  alias vim=\"nvim\"
  alias vi=\"nvim\"
  alias vimdiff=\"nvim -d\"
  export EDITOR=\$(which nvim)

  " >>$HOME/.zshrc
  mark_step "brew_install_neovim"
else
  echo -e "${GREEN}Skipping Neovim installation, already completed.${NC}"
fi

if ! check_step "lazyvim"; then
  echo -e "${RED}Setting up lazyvim...${NC}"
  git clone http://github.com/hongzio/hongzio.github.io $HOME/.hongzio.github.io || {
    echo -e "${RED}Failed to clone hongzio.github.io${NC}"
    exit 1
  }
  mkdir -p $HOME/.config &>/dev/null
  ln -s $HOME/.hongzio.github.io/lazyvim $HOME/.config/lazyvim || {
    echo -e "${RED}Failed to link lazyvim${NC}"
    exit 1
  }
  echo "export NVIM_APPNAME=lazyvim" >>$HOME/.zshrc
  mark_step "lazyvim"
else
  echo -e "${GREEN}Skipping lazyvim setup, already completed.${NC}"
fi

apps=(
  "obsidian"
  "pronotes"
  "1password"
  "firefox"
  "raycast"
  "mas"
  "maccy"
  "rectangle"
  "hiddenbar"
  "surfshark"
  "font-hack-nerd-font"
)

for app in "${apps[@]}"; do
  # echo "Do you want to install $app? (y/n)"
  # read -r response
  # if [[ $response =~ ^([yY][eE][sS]|[yY])$ ]]; then
  #  $BREW_PATH install $app || { echo -e "${RED}Failed to install $app"; exit 1; }
  # fi
  if ! check_step "$app"; then
    echo -e "${RED}Installing $app...${NC}"
    $BREW_PATH install $app || {
      echo -e "${RED}Failed to install $app${NC}"
      exit 1
    }
    mark_step "$app"
  else
    echo -e "${GREEN}Skipping $app installation, already completed.${NC}"
  fi
done

if ! check_step "app_store_apps"; then
  echo -e "${RED}Do you want to install apps from App Store? (${GREEN}y${RED}/${GREEN}n${RED})${NC}"
  read -r response
  if [[ $response =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo -e "${RED}Installing apps from App Store...${NC}"
    mas install 937984704 # Amphetamine
  fi
  mark_step "app_store_apps"
else
  echo -e "${GREEN}Skipping App Store apps installation, already completed.${NC}"
fi

if ! check_step "zshrc_setup"; then
  echo -e "${RED}Setting up zshrc...${NC}"

  # setup plugins
  sed -i '' 's/plugins=(git zsh-syntax-highlighting zsh-autosuggestions)/plugins=(git zsh-syntax-highlighting zsh-autosuggestions fzf zoxide asdf direnv macos)/' $HOME/.zshrc
  mark_step "zshrc_setup"
else
  echo -e "${GREEN}Skipping zshrc setup, already completed.${NC}"
fi

if ! check_step "dock_cleanup"; then
  echo -e "${RED}Removing all apps from dock...${NC}"
  defaults write com.apple.dock persistent-apps -array
  killall Dock
  mark_step "dock_cleanup"
else
  echo -e "${GREEN}Skipping dock cleanup, already completed.${NC}"
fi

if ! check_step "press_and_hold"; then
  echo -e "${RED}Disabling press and hold...${NC}"
  defaults write -g ApplePressAndHoldEnabled -bool false
  mark_step "press_and_hold"
else
  echo -e "${GREEN}Skipping press and hold disable, already completed.${NC}"
fi

if ! check_step "key_bindings"; then
  echo -e "${RED}Setting up key bindings...${NC}"
  mkdir -p $HOME/Library/KeyBindings/
  curl hongzio.com/DefaultkeyBinding.dict >$HOME/Library/KeyBindings/DefaultkeyBinding.dict
  mark_step "key_bindings"
else
  echo -e "${GREEN}Skipping key bindings setup, already completed.${NC}"
fi

echo -e "${RED}Finished!${NC}"
