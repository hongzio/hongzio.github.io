-- Treesitter incremental selection: grow/shrink the visual selection to the
-- enclosing syntax node. nvim-treesitter's `main` branch dropped its
-- incremental_selection module, so this is a small self-contained version
-- (zero extra plugins).
local M = {}

-- Stack of selected nodes, innermost .. outermost.
local history = {}

local function same_range(a, b)
  local a1, a2, a3, a4 = a:range()
  local b1, b2, b3, b4 = b:range()
  return a1 == b1 and a2 == b2 and a3 == b3 and a4 == b4
end

-- Set a charwise visual selection covering node's range.
local function select_node(node)
  vim.cmd('normal! \27') -- leave visual mode if we're in it
  local sr, sc, er, ec = node:range()
  vim.api.nvim_win_set_cursor(0, { sr + 1, sc })
  vim.cmd('normal! v')

  -- End column is exclusive; the last selected char sits at ec-1. When ec == 0
  -- the node ends at the start of `er`, i.e. the end of the previous line.
  local lr, lc = er, ec - 1
  if lc < 0 then
    lr = er - 1
    lc = #(vim.api.nvim_buf_get_lines(0, lr, lr + 1, false)[1] or '') - 1
  end
  local endline = vim.api.nvim_buf_get_lines(0, lr, lr + 1, false)[1] or ''
  lc = math.min(math.max(lc, 0), math.max(#endline - 1, 0))
  vim.api.nvim_win_set_cursor(0, { lr + 1, lc })
end

-- Start selection from the node under the cursor.
function M.init()
  local ok, node = pcall(vim.treesitter.get_node)
  if not ok or not node then return end
  history = { node }
  select_node(node)
end

-- Expand to the nearest ancestor that is strictly larger.
function M.expand()
  local node = history[#history]
  if not node then return M.init() end
  local parent = node:parent()
  while parent and same_range(parent, node) do
    parent = parent:parent()
  end
  if not parent then return end -- already at the root
  history[#history + 1] = parent
  select_node(parent)
end

-- Shrink back to the previously selected (smaller) node.
function M.shrink()
  if #history > 1 then
    history[#history] = nil
  end
  local node = history[#history]
  if node then select_node(node) end
end

local map = vim.keymap.set
-- <C-l> expands (normal: start selection, visual: grow to parent), <C-h>
-- shrinks. <C-l> overrides window-right (<C-w>l still works). Shrink is
-- VISUAL-only <C-h>, so normal-mode window-left <C-h> is unaffected.
map('n', '<C-l>', M.init, { desc = 'Select node (treesitter)' })
map('x', '<C-l>', M.expand, { desc = 'Expand selection' })
map('x', '<C-h>', M.shrink, { desc = 'Shrink selection' })

return M
