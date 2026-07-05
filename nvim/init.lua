-- nvim :: minimal, high-performance Neovim (default config in ~/.config/nvim).
-- Requires Neovim 0.12+ for vim.pack.

-- [perf] Enable the experimental Lua module loader / bytecode cache. Must run
-- before any require() so subsequent modules are cached.
vim.loader.enable()

-- Leader must be set before plugins/keymaps are loaded.
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '

require('options')
require('keymaps')
require('autosave')
require('plugins')
