-- monokai-pro: Monokai Pro palette (the `pro` filter — bg #2d2a2e, warmer,
-- slightly softer than classic Monokai).
--
-- NOTE: each filter has its own colors entrypoint. `monokai-pro` selects `pro`;
-- other filters use `monokai-pro-<filter>` (classic, machine, ristretto, ...).
require('monokai-pro').setup({})

-- pcall-guard so a first-launch race (plugin freshly cloned) can't error out;
-- falls back to a builtin scheme until the next start.
if not pcall(vim.cmd.colorscheme, 'monokai-pro') then
  vim.cmd.colorscheme('habamax')
end

-- Keep syntax highlighting readable inside diffs. In diff mode the whole added
-- (or changed) line gets the Diff* attributes layered on top, so any `fg` on
-- those groups wins over the treesitter fg and the hunk reads as one flat
-- green/orange block. Drop the fg and keep only a tinted bg, so the hunk is
-- still obvious from its background while the code keeps its own colors.
--
-- The scheme's own Diff* fg is reused as the tint source, blended into the
-- Normal background: the hue tracks whatever scheme/filter is loaded, and only
-- ALPHA below controls how bright the stripes are. Upstream's own bg sits around
-- 0.05, which is nearly invisible once the fg is gone.
local ALPHA = 0.4       -- DiffAdd / DiffChange / DiffDelete stripe intensity
local ALPHA_TEXT = 0.65 -- DiffText, i.e. the changed region *within* a line

local function blend(fg, bg, alpha)
  local function chan(shift)
    local f = math.floor(fg / shift) % 256
    local b = math.floor(bg / shift) % 256
    return math.floor(b + (f - b) * alpha + 0.5)
  end
  return string.format('#%02x%02x%02x', chan(65536), chan(256), chan(1))
end

local function tint_diff_only()
  local normal = vim.api.nvim_get_hl(0, { name = 'Normal', link = false })
  local bg = normal.bg or 0x000000

  local tints = {}
  for _, group in ipairs({ 'DiffAdd', 'DiffChange', 'DiffDelete' }) do
    local hl = vim.api.nvim_get_hl(0, { name = group, link = false })
    tints[group] = hl.fg
    if hl.fg then
      hl.bg = blend(hl.fg, bg, ALPHA)
      hl.fg = nil
    end
    vim.api.nvim_set_hl(0, group, hl)
  end

  -- DiffText marks the changed span inside a DiffChange line, so it borrows
  -- DiffChange's hue at a higher alpha to stand out against it.
  if tints.DiffChange then
    vim.api.nvim_set_hl(0, 'DiffText', {
      bg = blend(tints.DiffChange, bg, ALPHA_TEXT),
      bold = true,
    })
  end
end

vim.api.nvim_create_autocmd('ColorScheme', {
  group = vim.api.nvim_create_augroup('DiffKeepSyntax', { clear = true }),
  callback = tint_diff_only,
})
tint_diff_only()
