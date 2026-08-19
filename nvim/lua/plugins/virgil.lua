-- virgil.nvim: notes pinned onto code lines, readable and writable by agents
-- over an RPC socket. Installed via vim.pack in plugins/init.lua.
--
-- plugin/virgil.lua wires the commands, <Plug> maps and the RPC socket (on
-- VimEnter) by itself; setup() is only for what the defaults leave off.
require('virgil').setup({
  -- without an agent a question is only marked, never dispatched
  question = { agent = 'claude' },
})

local map = vim.keymap.set

-- Notes.
map({ 'n', 'x' }, '<leader>vv', '<Plug>(virgil-note)', { desc = 'Virgil note' })
map('n', '<leader>ve', '<Plug>(virgil-edit)', { desc = 'Virgil edit note at cursor' })
map('n', '<leader>vx', '<Plug>(virgil-remove)', { desc = 'Virgil delete note at cursor' })
map('n', '<leader>vt', '<Plug>(virgil-toggle)', { desc = 'Virgil toggle visibility' })
map('n', '<leader>vl', '<Cmd>Virgil notes<CR>', { desc = 'Virgil list notes' })

-- Replies. vE/vX are the uppercase pair of ve/vx: same verb, one level down.
map('n', '<leader>vc', '<Plug>(virgil-reply)', { desc = 'Virgil reply to note at cursor' })
map('n', '<leader>vE', '<Plug>(virgil-reply-edit)', { desc = 'Virgil edit a reply' })
map('n', '<leader>vX', '<Plug>(virgil-reply-remove)', { desc = 'Virgil delete a reply' })

-- Questions. v? lists them because vq already means quit; a brand-new
-- question is <C-q> inside the composer, which needs no mapping here.
map('n', '<leader>va', '<Plug>(virgil-ask)', { desc = 'Virgil ask about note at cursor' })
map('n', '<leader>v?', '<Cmd>Virgil questions<CR>', { desc = 'Virgil list questions' })

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
