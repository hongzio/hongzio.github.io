-- multicursor.nvim: VSCode-style multiple cursors, pure Lua.
local mc = require('multicursor-nvim')
mc.setup()

local map = vim.keymap.set

-- Expand cursors up / down a line (Ctrl+Arrow works via Ghostty's kitty
-- keyboard protocol). Works from normal and visual mode.
map({ 'n', 'x' }, '<C-Up>', function() mc.lineAddCursor(-1) end, { desc = 'Add cursor above' })
map({ 'n', 'x' }, '<C-Down>', function() mc.lineAddCursor(1) end, { desc = 'Add cursor below' })

-- Add a cursor at the next/prev occurrence of the word under cursor (or the
-- visual selection) — VSCode's Cmd/Ctrl+D.
map({ 'n', 'x' }, '<C-n>', function() mc.matchAddCursor(1) end, { desc = 'Add cursor: next match' })
map({ 'n', 'x' }, '<leader>mp', function() mc.matchAddCursor(-1) end, { desc = 'Add cursor: prev match' })

-- Skip the current match and move the cursor to the next/prev one.
map({ 'n', 'x' }, '<leader>ms', function() mc.matchSkipCursor(1) end, { desc = 'Skip match, go next' })

-- Select ALL occurrences of the word/selection at once (Cmd+Shift+L).
map({ 'n', 'x' }, '<leader>mA', function() mc.matchAllAddCursors() end, { desc = 'Add cursors: all matches' })

-- Restore the cursors cleared by the last <Esc>.
map('n', '<leader>mr', function() mc.restoreCursors() end, { desc = 'Restore cursors' })

-- Alt+click to place/remove a cursor (VSCode-style mouse multicursor).
map('n', '<M-LeftMouse>', mc.handleMouse, { desc = 'Toggle cursor at mouse' })
map('n', '<M-LeftDrag>', mc.handleMouseDrag)
map('n', '<M-LeftRelease>', mc.handleMouseRelease)

-- These maps are ACTIVE ONLY while there are multiple cursors, so they don't
-- shadow the global bindings (e.g. <Esc> = :nohlsearch) the rest of the time.
mc.addKeymapLayer(function(layer)
  -- Jump the "real" cursor between the multicursors.
  layer({ 'n', 'x' }, '<left>', mc.prevCursor, { desc = 'Prev cursor' })
  layer({ 'n', 'x' }, '<right>', mc.nextCursor, { desc = 'Next cursor' })
  -- Remove the cursor under the main one.
  layer({ 'n', 'x' }, '<leader>x', mc.deleteCursor, { desc = 'Delete cursor' })
  layer({ 'n', 'x' }, '<C-p>', mc.deleteCursor, { desc = 'Delete cursor' })
  -- First <Esc> disables cursors (move freely), second clears them.
  layer('n', '<esc>', function()
    if not mc.cursorsEnabled() then
      mc.enableCursors()
    else
      mc.clearCursors()
    end
  end)
end)
