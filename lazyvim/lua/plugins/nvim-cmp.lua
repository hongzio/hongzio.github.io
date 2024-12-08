return {
  "hrsh7th/nvim-cmp",
  dependencies = { "hrsh7th/cmp-emoji", "onsails/lspkind.nvim" },
  ---@param opts cmp.ConfigSchema
  opts = function(_, opts)
    local cmp = require("cmp")
    local cmp_window = require("cmp.config.window")
    opts.mapping = vim.tbl_extend("force", opts.mapping, {
      ["<C-b>"] = cmp.mapping.scroll_docs(-4),
      ["<C-f>"] = cmp.mapping.scroll_docs(4),
      ["<Tab>"] = cmp.mapping.confirm({ select = true }),
      ["<CR>"] = cmp.mapping(function(fallback)
        cmp.abort()
        fallback()
      end, { "i", "s" }),
      ["<C-k>"] = cmp.mapping.select_prev_item(),
      ["<C-j>"] = cmp.mapping.select_next_item(),
    })

    table.insert(opts.sources, { name = "emoji" })
    table.insert(opts.sources, 1, {
      name = "copilot",
      group_index = 1,
      priority = 100,
    })
    table.insert(opts.sources, 1, {
      name = "codeium",
      group_index = 1,
      priority = 100,
    })
    opts.window = {
      completion = cmp_window.bordered(),
      documentation = cmp_window.bordered(),
    }
    local lspkind = require("lspkind")
    opts.formatting.format = lspkind.cmp_format({
      mode = "symbol_text",
      max_width = 50,
      symbol_map = {
        Copilot = "",
        Codeium = "",
      },
    })

    vim.api.nvim_create_autocmd("CursorHoldI", {
      callback = function()
        require("cmp").complete()
      end,
    })
    vim.o.updatetime = 1000
  end,
}
