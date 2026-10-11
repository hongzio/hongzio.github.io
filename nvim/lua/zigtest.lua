-- Run Zig tests from the current buffer and put failures -- and passing runs
-- that printed something -- in the quickfix list.
--
-- Two invocations are kept on purpose, because they are not interchangeable:
--   * `zig test <file>` compiles that single file as its own root module. It
--     reaches tests that no `build.zig` step collects (a file nothing imports
--     yet), but breaks the moment the file `@import`s a package module.
--   * `zig build test` uses the real module graph, so it is the right answer
--     once the file is wired in -- but it only runs what the build script
--     actually reaches.
--
-- `zig` is resolved from PATH, same rule as the zls config: no version manager
-- leaks in here, mise's shell activation already puts it there.

local M = {}

-- Matches, in order: compile diagnostics, and the stack frames the test runner
-- prints on a failed assertion ("file:line:col: 0xADDR in name (test)").
-- Everything else -- source echoes, carets, the "N passed" summary -- falls
-- through as a non-jumpable text entry, which keeps the quickfix readable as a
-- log while `]q` still only stops on real locations.
local EFM = table.concat({
  '%f:%l:%c: %trror: %m',
  '%f:%l:%c: %tarning: %m',
  '%f:%l:%c: %tote: %m',
  '%f:%l:%c: 0x%*[0-9a-f] in %m',
}, ',')

-- What the test runner itself prints on a passing run when stderr is not a TTY
-- (lib/compiler/test_runner.zig). Any other line came from the tests: a
-- std.debug.print lands inline ("1/1 md5.decltest.Md5...[Hell]OK") or on lines
-- of its own, and that is what makes a passing run worth a window.
local RUNNER_LINES = {
  '^%d+/%d+ .*%.%.%.OK$',
  '^%d+/%d+ .*%.%.%.SKIP$',
  '^All %d+ tests passed%.$',
  '^%d+ passed; %d+ skipped; %d+ failed%.$',
  '^%d+ fuzz tests found%.$',
}

local function has_test_output(lines)
  for _, line in ipairs(lines) do
    local from_runner = false
    for _, pat in ipairs(RUNNER_LINES) do
      if line:find(pat) then
        from_runner = true
        break
      end
    end
    if not from_runner then return true end
  end
  return false
end

local state = { job = nil, last = nil }

local function root_of(buf)
  return vim.fs.root(buf, { 'build.zig', 'build.zig.zon', '.git' }) or vim.fn.getcwd()
end

-- zig prints paths relative to the cwd it ran in; quickfix would resolve them
-- against nvim's cwd, which is not necessarily the project root. Root them here
-- so the list is correct no matter where nvim was started.
local function absolutize(line, root)
  local path, rest = line:match('^([^:]+):(%d+:%d+:.*)$')
  if path and path:sub(1, 1) ~= '/' then
    return root .. '/' .. path .. ':' .. rest
  end
  return line
end

local function to_items(lines, root)
  local items = vim.fn.getqflist({ lines = lines, efm = EFM }).items
  -- Drop jumpable frames outside the project (std, cached deps). A failed
  -- assertion always prints std/testing.zig first, so without this `]q` lands
  -- in the standard library instead of on your own failing line. Non-jumpable
  -- text entries are kept, so the trace still reads in full.
  return vim.tbl_filter(function(it)
    if it.valid == 0 or it.bufnr == 0 then return true end
    local name = vim.api.nvim_buf_get_name(it.bufnr)
    return name == '' or vim.startswith(name, root)
  end, items)
end

local function run(buf, cmd, label)
  -- A new run supersedes an in-flight one; spamming the key should not pile up
  -- compilations that all race to write the same quickfix list.
  if state.job then
    state.job:kill('sigterm')
    state.job = nil
  end
  state.last = { buf = buf, cmd = cmd, label = label }

  local root = root_of(buf)
  vim.notify(label .. ' ...', vim.log.levels.INFO, { title = 'zig test' })

  local job
  job = vim.system(cmd, { cwd = root, text = true }, vim.schedule_wrap(function(res)
    -- A superseded run still exits through here once killed. Its output is
    -- stale and state.job already belongs to the newer run, so leave both be.
    if state.job ~= job then return end
    state.job = nil

    local lines = vim.split((res.stdout or '') .. (res.stderr or ''), '\n', { trimempty = true })
    for i, line in ipairs(lines) do
      -- A NUL turns the line into a Blob on its way to Vimscript and quickfix
      -- drops it without a word; printing a zero-filled buffer does exactly
      -- that. Show NULs the way Vim itself would.
      lines[i] = absolutize((line:gsub('%z', '^@')), root)
    end

    vim.fn.setqflist({}, 'r', { title = label, items = to_items(lines, root) })

    -- vim.system reports a signal-killed process as code 0, so a run that died
    -- to an external kill (OOM, a stray `kill`) would otherwise read as a pass.
    if res.code == 0 and res.signal == 0 then
      -- The log is in the list either way (`:copen` shows it); only a pass
      -- that printed something opens it, so a silent pass stays silent.
      if has_test_output(lines) then
        vim.cmd('copen')
        vim.cmd('wincmd p')
        vim.notify(label .. ' -- passed (output in quickfix)', vim.log.levels.INFO, { title = 'zig test' })
      else
        vim.cmd('cclose')
        vim.notify(label .. ' -- passed', vim.log.levels.INFO, { title = 'zig test' })
      end
      return
    end

    -- Open the list but hand focus back: you almost always want to keep editing
    -- and step through with ]q, not start inside the quickfix window.
    vim.cmd('copen')
    vim.cmd('wincmd p')
    vim.notify(label .. ' -- failed', vim.log.levels.ERROR, { title = 'zig test' })
  end))
  state.job = job
end

-- Name of the `test` block the cursor sits inside, or nil. Handles all three
-- forms: `test "name"`, `test someDecl`, and the anonymous `test {}` (nil).
local function test_name_at_cursor(buf)
  local ok, parser = pcall(vim.treesitter.get_parser, buf, 'zig')
  if not ok or not parser then return nil, 'no zig parser' end

  local tree = parser:parse()[1]
  if not tree then return nil, 'no zig parser' end

  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  local node = tree:root():named_descendant_for_range(row - 1, col, row - 1, col)
  while node and node:type() ~= 'test_declaration' do
    node = node:parent()
  end
  if not node then return nil, 'cursor is not inside a test block' end

  for child in node:iter_children() do
    local t = child:type()
    if t == 'identifier' then
      return vim.treesitter.get_node_text(child, buf)
    elseif t == 'string' then
      for part in child:iter_children() do
        if part:type() == 'string_content' then
          return vim.treesitter.get_node_text(part, buf)
        end
      end
    end
  end
  return nil, 'anonymous test block has no name to filter on'
end

-- Run only the `test` block under the cursor.
--
-- `--test-filter` is a substring match against the fully qualified name
-- ("md5.test.md5 encrypt"), so a name that is a prefix of another will run both.
function M.nearest()
  local buf = vim.api.nvim_get_current_buf()
  local file = vim.api.nvim_buf_get_name(buf)
  local name, err = test_name_at_cursor(buf)
  if not name then
    vim.notify(err, vim.log.levels.WARN, { title = 'zig test' })
    return
  end
  run(buf, { 'zig', 'test', '--color', 'off', file, '--test-filter', name }, 'test "' .. name .. '"')
end

-- Run every `test` block in the current file, standalone.
function M.file()
  local buf = vim.api.nvim_get_current_buf()
  local file = vim.api.nvim_buf_get_name(buf)
  run(buf, { 'zig', 'test', '--color', 'off', file }, 'zig test ' .. vim.fn.fnamemodify(file, ':.'))
end

-- Run the build script's `test` step -- only the tests its module graph reaches.
function M.all()
  local buf = vim.api.nvim_get_current_buf()
  run(buf, { 'zig', 'build', 'test', '--color', 'off' }, 'zig build test')
end

function M.last()
  if not state.last then
    vim.notify('nothing to re-run yet', vim.log.levels.WARN, { title = 'zig test' })
    return
  end
  run(state.last.buf, state.last.cmd, state.last.label)
end

return M
