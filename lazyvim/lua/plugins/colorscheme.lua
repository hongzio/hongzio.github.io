return {
  {
    "sontungexpt/witch",
    priority = 1000,
    lazy = false,
    opts = {
      dim_inactive = {
        level = 0.8,
      }
    }
  },
  {
    "sainnhe/sonokai",
    enabled = false,
    opts = function()
      -- Apply custom highlights on colorscheme change.
      -- Must be declared before executing ':colorscheme'.
      local grpid = vim.api.nvim_create_augroup("custom_highlights_sonokai", {})
      vim.api.nvim_create_autocmd("ColorScheme", {
        group = grpid,
        pattern = "sonokai",
        callback = function()
          local config = vim.fn["sonokai#get_configuration"]()
          local palette = vim.fn["sonokai#get_palette"](config.style, config.colors_override)
          local set_hl = vim.fn["sonokai#highlight"]

          set_hl("Visual", palette.none, palette.black)
          set_hl("IncSearch", palette.bg0, palette.yellow)
          set_hl("Search", palette.none, palette.diff_yellow)
        end,
      })
    end,
  },
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "witch-dark",
    },
  },
  {
    "folke/tokyonight.nvim",
    enabled = false,
  },
}
