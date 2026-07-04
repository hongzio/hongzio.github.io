-- Editor options. Kept lean on purpose.
local o = vim.o

-- UI
o.number = true
o.relativenumber = true
o.signcolumn = 'yes'          -- avoid layout shift when signs appear
o.cursorline = true
o.termguicolors = true
o.scrolloff = 8
o.wrap = false
o.splitright = true
o.splitbelow = true
o.laststatus = 3              -- single global statusline

-- Editing
o.expandtab = true
o.shiftwidth = 4
o.tabstop = 4
o.smartindent = true
o.ignorecase = true
o.smartcase = true
o.undofile = true             -- persistent undo
o.swapfile = false
o.clipboard = 'unnamedplus'

-- [perf] Treesitter-based folding, opened by default.
o.foldmethod = 'expr'
o.foldexpr = 'v:lua.vim.treesitter.foldexpr()'
o.foldtext = ''
o.foldlevel = 99
o.foldlevelstart = 99

-- [perf] Faster CursorHold / update-driven features without hurting typing.
o.updatetime = 250
o.timeoutlen = 400

-- Diagnostics: virtual text is noisy; keep it minimal + fast.
vim.diagnostic.config({
  virtual_text = { current_line = true },
  severity_sort = true,
  underline = true,
})

-- [perf] Disable language providers we don't use. Skips runtime probing at
-- startup for python/ruby/perl/node remote plugins.
vim.g.loaded_python3_provider = 0
vim.g.loaded_ruby_provider = 0
vim.g.loaded_perl_provider = 0
vim.g.loaded_node_provider = 0

-- [perf] Disable rarely-used builtin plugins.
for _, plugin in ipairs({
  'gzip', 'zip', 'zipPlugin', 'tar', 'tarPlugin',
  'getscript', 'getscriptPlugin', 'vimball', 'vimballPlugin',
  'netrw', 'netrwPlugin', 'netrwSettings', 'netrwFileHandlers',
  '2html_plugin', 'logipat', 'rrhelper', 'matchit',
}) do
  vim.g['loaded_' .. plugin] = 1
end
