-- Auto-save: write named file buffers at natural pause points (leaving insert,
-- losing focus) and shortly after any change. Skips special buffers (oil,
-- terminals, help, ...), unnamed/readonly buffers, and anything unmodified.
local group = vim.api.nvim_create_augroup('nvim_autosave', { clear = true })

local function should_save(buf)
  return vim.api.nvim_buf_is_valid(buf)
    and vim.bo[buf].buftype == '' -- normal file buffer (excludes oil/acwrite/terminal/...)
    and vim.bo[buf].modifiable
    and not vim.bo[buf].readonly
    and vim.bo[buf].modified
    and vim.api.nvim_buf_get_name(buf) ~= ''
end

local function save(buf)
  if not should_save(buf) then return end
  -- Buffer-scoped write; runs BufWritePre/Post so gitsigns refreshes.
  vim.api.nvim_buf_call(buf, function()
    vim.cmd('silent! write')
  end)
end

-- Debounce change-triggered saves so rapid edits coalesce into a single write.
local timer = vim.uv.new_timer()
local function debounced_save(buf)
  timer:stop()
  timer:start(400, 0, vim.schedule_wrap(function() save(buf) end))
end

-- Immediate on pause points (infrequent).
vim.api.nvim_create_autocmd({ 'InsertLeave', 'FocusLost' }, {
  group = group,
  desc = 'Auto-save on pause',
  callback = function(args) save(args.buf) end,
})

-- Debounced after normal-mode edits (dd, p, macros, ...).
vim.api.nvim_create_autocmd('TextChanged', {
  group = group,
  desc = 'Auto-save shortly after a change',
  callback = function(args) debounced_save(args.buf) end,
})
