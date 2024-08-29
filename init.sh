#!/usr/bin/env bash

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

if ! xcode-select -p &> /dev/null; then
  echo -e "${GREEN}Command line tools are not installed. Installing...${NC}"
  xcode-select --install
  echo -e "${GREEN}After installing, run this script again.${NC}"
  echo -e "${GREEN}Run this script with
    ${RED}/bin/bash -c \"\$(curl hongzio.com/init.sh)\"${NC}"
  exit 0
fi

if ! command -v brew &> /dev/null; then
  echo -e "${GREEN}Homebrew is not installed. Installing...${NC}"
  echo -e "${RED}What version of Homebrew do you want to install? (${GREEN}local${RED}/${GREEN}global${RED})${NC}"
  read -r version
  if [[ $version == "local" ]]; then
    cd && mkdir .homebrew && curl -L https://github.com/Homebrew/brew/tarball/master | tar xz --strip 1 -C .homebrew || { echo -e "${RED}Failed to install homebrew${NC}"; exit 1; }
    echo -e "${GREEN}To set up binary path, add below to your shell configuration file:${NC}"
    echo -e "${RED}export PATH=\$HOME/.homebrew/bin:\$PATH${NC}"
    export PATH=$HOME/.homebrew/bin:$PATH
  elif [[ $version == "global" ]]; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || { echo -e "${RED}Failed to install homebrew${NC}"; exit 1; }
  else
    exit 1
  fi
else
  echo -e "${GREEN}Homebrew is already installed.${NC}"
fi
BREW_PATH=$(command -v brew)

$BREW_PATH install karabiner-elements || { echo -e "${RED}Failed to install karabiner-elements"; exit 1; }
echo -e "${RED}Karabiner-Elements is installed. Please set up the configuration manually and System Preferences${NC}"


echo -e "\n${RED}Installing Git...${NC}"
$BREW_PATH install git || { echo -e "${RED}Failed to install git"; exit 1; }

echo -e "\n${RED}Installing Zsh...${NC}"
$BREW_PATH install zsh zsh-completions || { echo -e "${RED}Failed to install zsh"; exit 1; }
RUNZSH=no sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" || { echo -e "${RED}Failed to install oh-my-zsh${NC}"; exit 1; }
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting || { echo -e "${RED}Failed to install zsh-syntax-highlighting${NC}"; exit 1; }
git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions || { echo -e "${RED}Failed to install zsh-autosuggestions${NC}"; exit 1; }
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k || { echo -e "${RED}Failed to install powerlevel10k${NC}"; exit 1; }

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
" >> $HOME/.zshrc


apps=(
  "iterm2"
  "fzf"
  "zoxide"
  "asdf"
  "xz"  # for python build
  "direnv"
  "tig"
  "neovim"

  "notion"
  "1password"
  "firefox"
  "raycast"
  "mas"
  "maccy"
  "rectangle"
  "hiddenbar"
  "homebrew/cask-fonts/font-d2coding"
)

for app in "${apps[@]}"; do
  echo -e "${RED}Installing $app...${NC}"
  # echo "Do you want to install $app? (y/n)"
  # read -r response
  # if [[ $response =~ ^([yY][eE][sS]|[yY])$ ]]; then
  #  $BREW_PATH install $app || { echo -e "${RED}Failed to install $app"; exit 1; }
  # fi
  $BREW_PATH install $app || { echo -e "${RED}Failed to install $app"; exit 1; }
done

echo -e "${RED}Do you want to install apps from App Store? (${GREEN}y${RED}/${GREEN}n${RED})${NC}"
read -r response
if [[ $response =~ ^([yY][eE][sS]|[yY])$ ]]; then
  echo -e "${RED}Installing apps from App Store...${NC}"
  mas install 937984704  # Amphetamine
fi

echo -e "${RED}Setting up zshrc...${NC}"
echo "

# key bindings
eval \"\$(fzf --zsh)\" # fzf key bindings
eval \"\$(zoxide init zsh)\" # zoxide key bindings
. $(brew --prefix asdf)/libexec/asdf.sh # asdf key bindings
eval \"\$(direnv hook zsh)\" # direnv key bindings

# neovim
alias vim=\"nvim\"
alias vi=\"nvim\"
alias vimdiff=\"nvim -d\"
export EDITOR=\$(which nvim)

" >> $HOME/.zshrc

# setup plugins
sed -i '' 's/plugins=(git zsh-syntax-highlighting zsh-autosuggestions)/plugins=(git zsh-syntax-highlighting zsh-autosuggestions fzf zoxide asdf direnv macos)/' $HOME/.zshrc

echo -e "${RED}Removing all apps from dock...${NC}"
defaults write com.apple.dock persistent-apps -array
killall Dock

echo -e "${RED}Disabling press and hold...${NC}"
defaults write -g ApplePressAndHoldEnabled -bool false

echo -e "${RED}Setting up dotfiles...${NC}"
curl hongzio.com/tigrc > $HOME/.tigrc

echo -e "${RED}Setting up key bindings...${NC}"
mkdir -p $HOME/Library/KeyBindings/
curl hongzio.com/DefaultkeyBinding.dict > $HOME/Library/KeyBindings/DefaultkeyBinding.dict

echo -e "${RED}Setting up git...${NC}"
git config --global user.name hongzio
git config --global user.email hongzio@user.noreply.github.com
git config --global core.excludesFile $HOME/.gitignore
git config --global init.defaultBranch main
git config --global url."git@github.com:".insteadOf "https://github.com/"

echo ".tool-versions
.direnv
.envrc
.idea
.DS_Store" > $HOME/.gitignore

echo -e "${RED}Finished!${NC}"
