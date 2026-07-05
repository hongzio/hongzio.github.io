-- harpoon (harpoon2): pin a small set of files and jump straight to them.
-- Complements fzf-lua (search) with a fixed, ordered working set.
--
-- Keys avoid the taken canonical harpoon spots: <leader>h* is git hunks,
-- <leader>a is parameter swap, and <C-h/j/k/l> are motions/windows. So the
-- quick slots live on <leader>1..4 and management under the <leader>j prefix.
local harpoon = require('harpoon')
harpoon:setup()

local map = vim.keymap.set
map('n', '<leader>ja', function() harpoon:list():add() end, { desc = 'Harpoon add file' })
map('n', '<leader>jj', function() harpoon.ui:toggle_quick_menu(harpoon:list()) end, { desc = 'Harpoon menu' })
map('n', '<leader>jp', function() harpoon:list():prev() end, { desc = 'Harpoon prev' })
map('n', '<leader>jn', function() harpoon:list():next() end, { desc = 'Harpoon next' })

-- Jump straight to pinned slots 1-4.
for i = 1, 4 do
  map('n', '<leader>' .. i, function() harpoon:list():select(i) end, { desc = 'Harpoon file ' .. i })
end
