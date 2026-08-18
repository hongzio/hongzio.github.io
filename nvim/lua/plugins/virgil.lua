-- virgil.nvim: notes pinned onto code lines, readable and writable by agents
-- over an RPC socket. Installed via vim.pack in plugins/init.lua.
--
-- No setup() call: plugin/virgil.lua wires the commands, <Plug> maps and the
-- RPC socket (on VimEnter) by itself, and the defaults are the ones we want.
local map = vim.keymap.set

-- Notes.
map({ 'n', 'x' }, '<leader>vv', '<Plug>(virgil-note)', { desc = 'Virgil note' })
map('n', '<leader>ve', '<Plug>(virgil-edit)', { desc = 'Virgil edit note at cursor' })
map('n', '<leader>vx', '<Plug>(virgil-remove)', { desc = 'Virgil delete note at cursor' })
map('n', '<leader>vt', '<Plug>(virgil-toggle)', { desc = 'Virgil toggle visibility' })
map('n', '<leader>vl', '<Cmd>Virgil notes<CR>', { desc = 'Virgil list notes' })

-- Changesets. <leader>vR passes HEAD explicitly because a bare `:Virgil
-- review` opens the picker rather than the working tree.
map('n', '<leader>vr', '<Cmd>Virgil review<CR>', { desc = 'Virgil pick a changeset' })
map('n', '<leader>vR', '<Cmd>Virgil review HEAD<CR>', { desc = 'Virgil review worktree' })
map('n', '<leader>vf', '<Cmd>Virgil files<CR>', { desc = 'Virgil changed files' })
map('n', '<leader>vs', '<Cmd>Virgil sidebar<CR>', { desc = 'Virgil toggle file list' })
map('n', '<leader>vq', '<Cmd>Virgil quit<CR>', { desc = 'Virgil close changeset tabs' })

-- Motions. Changeset files sit on ]v/[v rather than ]f/[f, which
-- nvim-treesitter-textobjects already claims for function motions.
map('n', ']n', '<Plug>(virgil-next-note)', { desc = 'Next virgil note' })
map('n', '[n', '<Plug>(virgil-prev-note)', { desc = 'Prev virgil note' })
map('n', ']v', '<Plug>(virgil-next-file)', { desc = 'Next virgil changeset file' })
map('n', '[v', '<Plug>(virgil-prev-file)', { desc = 'Prev virgil changeset file' })
