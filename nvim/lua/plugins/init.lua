-- Plugin management via the builtin vim.pack (Neovim 0.12+). Sources are
-- cloned on first launch; run :Pack update later to update them.
vim.pack.add({
  -- Fuzzy finder (fast, fzf-native).
  { src = 'https://github.com/ibhagwan/fzf-lua' },

  -- QoL toolkit: bigfile, quickfile, notifier, ...
  { src = 'https://github.com/folke/snacks.nvim' },

  -- mini.nvim: we only use a couple of its modules (statusline, icons).
  { src = 'https://github.com/echasnovski/mini.nvim' },

  -- Treesitter: `main` branch is the current rewrite.
  { src = 'https://github.com/nvim-treesitter/nvim-treesitter', version = 'main' },

  -- Treesitter text objects + motions (next/prev function, etc.). `main`
  -- branch to match nvim-treesitter's main branch.
  { src = 'https://github.com/nvim-treesitter/nvim-treesitter-textobjects', version = 'main' },

  -- Sticky context header: shows the enclosing function/block at the top of
  -- the window. Drives off vim.treesitter directly, so `main`-branch safe.
  { src = 'https://github.com/nvim-treesitter/nvim-treesitter-context' },

  -- Completion (Rust fuzzy matcher). Pin to the 1.x release line so blink
  -- pulls its prebuilt fuzzy binary instead of needing a cargo build.
  { src = 'https://github.com/saghen/blink.cmp', version = vim.version.range('1') },

  -- Colorscheme: Monokai (matches bat's default theme used in the fzf preview).
  { src = 'https://github.com/loctvl842/monokai-pro.nvim' },

  -- Multicursor (VSCode-style): pure Lua, minimal.
  { src = 'https://github.com/jake-stewart/multicursor.nvim' },

  -- Git: hunk signs, inline blame, hunk preview/stage/reset. Pure Lua, fast.
  { src = 'https://github.com/lewis6991/gitsigns.nvim' },

  -- File explorer: edit the filesystem as a buffer.
  { src = 'https://github.com/stevearc/oil.nvim' },

  -- GitHub Copilot: inline AI suggestions (ghost text). Pure Lua client.
  { src = 'https://github.com/zbirenbaum/copilot.lua' },

  -- Smart <C-a>/<C-x>: increment/decrement numbers, dates, booleans, operators,
  -- and more, with per-filetype rule groups.
  { src = 'https://github.com/monaqa/dial.nvim' },

  -- Label-based motion: jump anywhere on screen in a few keystrokes (s / S).
  { src = 'https://github.com/folke/flash.nvim' },
})

-- Order matters: blink first (LSP capabilities), then the rest.
require('plugins.icons')
require('plugins.colorscheme')
require('plugins.blink')
require('plugins.lsp')
require('plugins.treesitter')
require('plugins.treesitter-textobjects')
require('plugins.treesitter-incremental')
require('plugins.treesitter-context')
require('plugins.fzf')
require('plugins.snacks')
require('plugins.statusline')
require('plugins.surround')
require('plugins.pairs')
require('plugins.multicursor')
require('plugins.gitsigns')
require('plugins.oil')
require('plugins.copilot')
require('plugins.dial')
require('plugins.flash')
