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
o.inccommand = 'split'        -- live preview for :s, with a scratch split
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

-- Color the diagnostic *text* itself, not just the underline. By default the
-- DiagnosticUnderline* groups only set the undercurl color (`sp`) and leave the
-- text on its syntax fg, so an error reads in normal text with a faint squiggle.
-- Pull the fg from each severity's Diagnostic* group and apply it (bold on
-- errors) so errors go red-bold, warnings yellow, etc. Re-run on ColorScheme so
-- it survives scheme reloads.
local function style_diagnostic_text()
  local specs = {
    { under = 'DiagnosticUnderlineError', from = 'DiagnosticError', bold = true },
    { under = 'DiagnosticUnderlineWarn', from = 'DiagnosticWarn', bold = false },
    { under = 'DiagnosticUnderlineInfo', from = 'DiagnosticInfo', bold = false },
    { under = 'DiagnosticUnderlineHint', from = 'DiagnosticHint', bold = false },
  }
  for _, s in ipairs(specs) do
    local src = vim.api.nvim_get_hl(0, { name = s.from, link = false })
    local cur = vim.api.nvim_get_hl(0, { name = s.under, link = false })
    cur.fg = src.fg
    cur.bold = s.bold
    vim.api.nvim_set_hl(0, s.under, cur)
  end
end

vim.api.nvim_create_autocmd('ColorScheme', {
  group = vim.api.nvim_create_augroup('DiagnosticTextColor', { clear = true }),
  callback = style_diagnostic_text,
})
style_diagnostic_text()

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
