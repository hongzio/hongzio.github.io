return {
  {
    "nvim-neo-tree/neo-tree.nvim",
    opts = {
      filesystem = {
        window = {
          mappings = {
            ["<leader>ws"] = "open_split",
            ["<leader>wv"] = "open_vsplit",
          },
        },
      },
    },
  },
}
