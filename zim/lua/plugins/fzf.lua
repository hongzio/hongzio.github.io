-- fzf-lua: fuzzy finder. 'max-perf' profile favours native fzf performance and
-- disables the more expensive previewers/features by default.
local fzf = require('fzf-lua')
fzf.setup({ 'max-perf' })

local map = vim.keymap.set
map('n', '<leader>ff', fzf.files, { desc = 'Find files' })
map('n', '<leader>fg', fzf.live_grep, { desc = 'Live grep' })
map('n', '<leader>fb', fzf.buffers, { desc = 'Buffers' })
map('n', '<leader>fh', fzf.helptags, { desc = 'Help tags' })
map('n', '<leader>fr', fzf.resume, { desc = 'Resume last picker' })
map('n', '<leader>fd', fzf.diagnostics_document, { desc = 'Document diagnostics' })
map('n', '<leader>fs', fzf.lsp_document_symbols, { desc = 'Document symbols' })
map('n', '<leader>fS', fzf.lsp_live_workspace_symbols, { desc = 'Workspace symbols (live)' })
map('n', '<leader>/', fzf.blines, { desc = 'Search in buffer' })
map('n', '<leader><space>', fzf.files, { desc = 'Find files' })
