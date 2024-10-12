return {
  "hrsh7th/nvim-cmp",
  dependencies = { "hrsh7th/cmp-emoji" },
  ---@param opts cmp.ConfigSchema
  opts = function(_, opts)
    local cmp = require("cmp")
    opts.mapping = vim.tbl_extend("force", opts.mapping, {
      ["<Tab>"] = cmp.mapping.confirm({ select = true }),
      ["<CR>"] = cmp.mapping(function(fallback)
        cmp.abort()
        fallback()
      end, {"i", "s"})
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
  end,
}
