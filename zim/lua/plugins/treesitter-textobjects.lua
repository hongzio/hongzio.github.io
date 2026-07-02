-- Treesitter-based motions: jump between NAMED functions/methods only.
--
-- The `@function.outer` capture also matches anonymous function literals
-- (closures). We collect those nodes but keep only the ones that have a `name`
-- field, which excludes anonymous functions (e.g. Go `func_literal`, Lua
-- anonymous `function() end`).
require('nvim-treesitter-textobjects').setup({
  move = { set_jumps = true },
})

-- Collect named-function nodes in the buffer, sorted by start position.
local function named_functions(buf)
  local ok, parser = pcall(vim.treesitter.get_parser, buf)
  if not ok or not parser then return {} end
  local ok_q, query = pcall(vim.treesitter.query.get, parser:lang(), 'textobjects')
  if not ok_q or not query then return {} end
  local tree = (parser:parse() or {})[1]
  if not tree then return {} end

  local nodes = {}
  for id, node in query:iter_captures(tree:root(), buf, 0, -1) do
    if query.captures[id] == 'function.outer' then
      local name = node:field('name')
      if name and name[1] then -- has a name -> not anonymous
        nodes[#nodes + 1] = node
      end
    end
  end
  table.sort(nodes, function(a, b)
    local ar, ac = a:start()
    local br, bc = b:start()
    if ar ~= br then return ar < br end
    return ac < bc
  end)
  return nodes
end

-- Build a motion that jumps to the next/prev named function (start or end).
local function goto_named(dir, at_end)
  return function()
    local buf = vim.api.nvim_get_current_buf()
    local nodes = named_functions(buf)
    if #nodes == 0 then return end

    local cr, cc = unpack(vim.api.nvim_win_get_cursor(0))
    cr = cr - 1 -- to 0-indexed row

    local function pos(node)
      if at_end then return node:end_() end
      -- Land on the first char of the function NAME, not the `func`/`function`
      -- keyword. Nodes here always have a name field (anonymous were filtered).
      local name = node:field('name')[1]
      if name then return name:start() end
      return node:start()
    end
    local function after(r, c) return r > cr or (r == cr and c > cc) end

    local target
    local count = vim.v.count1
    if dir > 0 then
      for _, node in ipairs(nodes) do
        local r, c = pos(node)
        if after(r, c) then
          count = count - 1
          if count == 0 then target = { r, c } break end
        end
      end
    else
      for i = #nodes, 1, -1 do
        local r, c = pos(nodes[i])
        if not after(r, c) and not (r == cr and c == cc) then
          count = count - 1
          if count == 0 then target = { r, c } break end
        end
      end
    end
    if not target then return end

    if vim.api.nvim_get_mode().mode == 'n' then
      vim.cmd("normal! m'") -- add to jumplist so <C-o>/<C-i> work
    end
    vim.api.nvim_win_set_cursor(0, { target[1] + 1, math.max(target[2], 0) })
  end
end

local map = vim.keymap.set
local modes = { 'n', 'x', 'o' } -- normal, visual, operator-pending (e.g. d]f)

-- Named function start.
map(modes, ']f', goto_named(1, false), { desc = 'Next named function' })
map(modes, '[f', goto_named(-1, false), { desc = 'Prev named function' })
map(modes, '<C-j>', goto_named(1, false), { desc = 'Next named function' })
map(modes, '<C-k>', goto_named(-1, false), { desc = 'Prev named function' })
-- Named function end.
map(modes, ']F', goto_named(1, true), { desc = 'Next named function end' })
map(modes, '[F', goto_named(-1, true), { desc = 'Prev named function end' })
