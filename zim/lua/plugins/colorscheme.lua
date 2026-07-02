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
