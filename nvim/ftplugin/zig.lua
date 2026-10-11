-- Zig buffers: test-runner keymaps. The runner itself lives in lua/zigtest.lua
-- so this file, which is re-sourced for every zig buffer, only wires maps.

local zigtest = require('zigtest')
local map = vim.keymap.set

local function bmap(lhs, fn, desc)
  map('n', lhs, fn, { buffer = true, desc = desc })
end

bmap('<leader>tn', zigtest.nearest, 'Zig: test under cursor')
bmap('<leader>tf', zigtest.file, 'Zig: tests in this file')
bmap('<leader>ta', zigtest.all, 'Zig: zig build test')
bmap('<leader>tl', zigtest.last, 'Zig: re-run last test command')

-- Buffer-local :Test and <leader>t* are shared across languages: every
-- filetype with a test runner binds the same names to its own runner.
vim.api.nvim_buf_create_user_command(0, 'Test', function(opts)
  local fn = ({ nearest = zigtest.nearest, file = zigtest.file, all = zigtest.all, last = zigtest.last })[opts.args]
  if not fn then
    vim.notify('unknown action "' .. opts.args .. '" (nearest|file|all|last)', vim.log.levels.ERROR, { title = 'zig test' })
    return
  end
  fn()
end, {
  nargs = 1,
  complete = function() return { 'nearest', 'file', 'all', 'last' } end,
  desc = 'Run Zig tests (nearest|file|all|last)',
})
