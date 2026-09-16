-- fzf-lua: fuzzy finder. 'max-perf' profile favours native fzf performance and
-- disables the more expensive previewers/features by default.
local fzf = require('fzf-lua')
fzf.setup({
  'max-perf',
  -- Preview at the bottom so the list spans the full popup width and shows
  -- each entry's full path without truncation.
  winopts = {
    preview = {
      layout = 'vertical',
      vertical = 'down:75%',
    },
  },
  keymap = {
    -- max-perf uses the native (bat) previewer, so preview scrolling is an fzf
    -- action bound via --bind, not a builtin keymap. This overrides the default
    -- ctrl-d/ctrl-u list scroll to scroll the preview by half a page instead.
    fzf = {
      ['ctrl-d'] = 'preview-half-page-down',
      ['ctrl-u'] = 'preview-half-page-up',
    },
  },
})

local map = vim.keymap.set
map('n', '<leader>ff', fzf.files, { desc = 'Find files' })
map('n', '<leader>fg', fzf.live_grep, { desc = 'Live grep' })
map('n', '<leader>fb', fzf.buffers, { desc = 'Buffers' })
map('n', '<leader>fo', fzf.oldfiles, { desc = 'Recent files' })
map('n', '<leader>gh', fzf.git_bcommits, { desc = 'Git file history' })
map('n', '<leader>gH', fzf.git_commits, { desc = 'Git project commits' })
map('n', '<leader>fh', fzf.helptags, { desc = 'Help tags' })
map('n', '<leader>fr', fzf.resume, { desc = 'Resume last picker' })
map('n', '<leader>fd', fzf.diagnostics_document, { desc = 'Document diagnostics' })
map('n', '<leader>fs', fzf.lsp_document_symbols, { desc = 'Document symbols' })
map('n', '<leader>fS', fzf.lsp_live_workspace_symbols, { desc = 'Workspace symbols (live)' })
map('n', '<leader>/', fzf.blines, { desc = 'Search in buffer' })
map('n', '<leader><space>', fzf.files, { desc = 'Find files' })
-- Keymap pickers: <C-p> opens user mappings ("what did I customize"); ctrl-b
-- inside toggles to the builtin key commands ("what does this key do out of
-- the box") and back. Vim's builtin normal/insert/visual/... key commands
-- aren't mappings, so nvim_get_keymap (and therefore fzf.keymaps) can't see
-- them; the only enumeration is $VIMRUNTIME/doc/index.txt. Parse its
-- `|tag|  key  description` tables and jump to the help tag on enter.
local user_keymaps -- forward declaration: the two pickers toggle into each other

local function builtin_keys()
  -- Section markers => mode label. Parsing stops at the Ex-command section;
  -- builtin : commands are commands, not keys.
  local sections = {
    ['insert-index'] = 'i',
    ['normal-index'] = 'n',
    ['operator-pending-index'] = 'o',
    ['visual-index'] = 'v',
    ['ex-edit-index'] = 'c',
    ['terminal-mode-index'] = 't',
  }

  local entries, tag_of = {}, {}
  local mode, tag, key, desc

  local function flush()
    if not tag then return end
    -- Note column (1 = motion, 2 = undoable) is a footnote ref, drop it.
    desc = desc:gsub('^%d%s%s+', '')
    local entry = string.format('%s %-22s %s', mode, key, desc)
    tag_of[entry] = tag
    -- fzf --ansi strips the color before matching/returning, so the colored
    -- and plain forms stay in sync as long as only the mode char is colored.
    table.insert(entries, require('fzf-lua.utils').ansi_codes.blue(mode)
      .. entry:sub(2))
    tag, key, desc = nil, nil, nil
  end

  for line in io.lines(vim.env.VIMRUNTIME .. '/doc/index.txt') do
    local marker = line:match('%*(%S+-index)%*')
    if marker == 'ex-cmd-index' then break end
    if sections[marker] then
      flush()
      mode = sections[marker]
    elseif mode then
      -- Long tags overflow their column, so tag/key can be separated by a
      -- lone space; key and description are always separated by a tab.
      local t, rest = line:match('^[|*]([^|*]+)[|*]%s?(.*)')
      if t then
        flush()
        local k, d = rest:match('^\t*([^\t]+)\t+%s*(.*)')
        if not k then
          -- A long key ("CTRL-R {regname}") can fill the line, pushing the
          -- whole description onto continuation lines.
          k, d = rest:match('^\t*(%S.-)%s*$'), ''
        end
        if k then tag, key, desc = t, k, d end
      elseif tag and line:match('^%s+%S') then
        local cont = line:match('^%s*(.-)%s*$')
        desc = desc == '' and cont or desc .. ' ' .. cont
      else
        flush()
      end
    end
  end
  flush()

  fzf.fzf_exec(entries, {
    prompt = 'BuiltinKeys> ',
    fzf_opts = {
      ['--no-multi'] = true,
      ['--header'] = 'enter: open :help │ ctrl-b: your keymaps',
    },
    actions = {
      enter = function(selected)
        local help_tag = selected[1] and tag_of[selected[1]]
        -- No fnameescape: it would escape the < in key-notation tags like
        -- <ScrollWheelDown>, which :help then fails to find.
        if help_tag then vim.cmd('help ' .. help_tag) end
      end,
      ['ctrl-b'] = function() user_keymaps() end,
    },
  })
end

user_keymaps = function()
  fzf.keymaps({
    fzf_opts = { ['--header'] = 'ctrl-b: builtin keys' },
    actions = { ['ctrl-b'] = builtin_keys },
  })
end
-- Note: while multicursor is active its layer claims <C-p> (delete cursor).
map('n', '<C-p>', user_keymaps, { desc = 'Keymaps' })
