-- General keymaps. Plugin-specific maps live next to their setup.
local map = vim.keymap.set

-- Clear search highlight.
map('n', '<Esc>', '<cmd>nohlsearch<CR>')

-- Window navigation. <C-j>/<C-k> are reassigned to function motions and <C-l>
-- to node-selection expand; use <C-w>h/j/k/l for splits.
map('n', '<C-h>', '<C-w>h')

-- Window ops under <leader>w (directional moves stay on <C-w>/<C-h> to avoid
-- duplication). <C-w> itself is untouched, so nothing is lost.
map('n', '<leader>w-', '<C-w>s', { desc = 'Split window (horizontal)' })
map('n', '<leader>w|', '<C-w>v', { desc = 'Split window (vertical)' })
map('n', '<leader>wc', '<C-w>c', { desc = 'Close window' })
map('n', '<leader>wq', '<C-w>q', { desc = 'Quit window' })
map('n', '<leader>wo', '<C-w>o', { desc = 'Only (close others)' })
map('n', '<leader>ww', '<C-w>w', { desc = 'Cycle to other window' })
map('n', '<leader>w=', '<C-w>=', { desc = 'Equalize window sizes' })
map('n', '<leader>wx', '<C-w>x', { desc = 'Exchange with next window' })
map('n', '<leader>wr', '<C-w>r', { desc = 'Rotate windows' })
map('n', '<leader>wT', '<C-w>T', { desc = 'Move window to new tab' })
map('n', '<leader>wH', '<C-w>H', { desc = 'Move window far left' })
map('n', '<leader>wJ', '<C-w>J', { desc = 'Move window far down' })
map('n', '<leader>wK', '<C-w>K', { desc = 'Move window far up' })
map('n', '<leader>wL', '<C-w>L', { desc = 'Move window far right' })

-- File-wise jumplist navigation. <C-o>/<C-i> walk the jumplist per cursor
-- position; <C-S-o>/<C-S-i> walk it per file: step until the buffer changes,
-- then (forward) keep going to the newest cursor position within that file so
-- both directions land where you last were in the file, not on its entry point.
-- Requires a terminal that speaks the Kitty keyboard protocol (Ghostty does) so
-- <C-S-i> is distinguishable from <C-i>.
local function jump_file(dir)
  local jl = vim.fn.getjumplist()
  local list, idx = jl[1], jl[2] -- idx is 0-based
  local start = vim.api.nvim_get_current_buf()

  -- Bail unless a different buffer exists in this direction, so we never wander
  -- the cursor around the current file when there is no other file to reach.
  local other = false
  if dir == 'back' then
    for li = idx, 1, -1 do
      if list[li].bufnr ~= start then other = true break end
    end
  else
    for li = idx + 1, #list do
      if list[li].bufnr ~= start then other = true break end
    end
  end
  if not other then return end

  -- Feed a jump key and report whether the cursor actually moved.
  local function step(k)
    local b0 = vim.api.nvim_get_current_buf()
    local p0 = vim.api.nvim_win_get_cursor(0)
    vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes(k, true, false, true), 'nx', false)
    local b1 = vim.api.nvim_get_current_buf()
    local p1 = vim.api.nvim_win_get_cursor(0)
    return not (b0 == b1 and p0[1] == p1[1] and p0[2] == p1[2])
  end

  local key = dir == 'back' and '<C-o>' or '<C-i>'
  repeat
    if not step(key) then return end
  until vim.api.nvim_get_current_buf() ~= start
  if dir == 'back' then return end -- back already lands on the newest entry

  -- Forward: advance to the newest cursor position within this file, backing off
  -- the moment a step would cross into another buffer.
  local target = vim.api.nvim_get_current_buf()
  while step('<C-i>') do
    if vim.api.nvim_get_current_buf() ~= target then
      step('<C-o>')
      return
    end
  end
end

map('n', '<C-S-o>', function() jump_file('back') end, { desc = 'Jump back one file' })
map('n', '<C-S-i>', function() jump_file('forward') end, { desc = 'Jump forward one file' })

-- Keep cursor centered on jumps.
map('n', '<C-d>', '<C-d>zz')
map('n', '<C-u>', '<C-u>zz')
map('n', 'n', 'nzzzv')
map('n', 'N', 'Nzzzv')

-- Move selected lines.
map('v', 'J', ":m '>+1<CR>gv=gv")
map('v', 'K', ":m '<-2<CR>gv=gv")

-- Diagnostics.
map('n', '<leader>e', vim.diagnostic.open_float, { desc = 'Line diagnostics' })
map('n', '<leader>q', vim.diagnostic.setloclist, { desc = 'Diagnostics to loclist' })
