return {
  {
    "nvim-neo-tree/neo-tree.nvim",
    keys = {
      {
        "<leader>e",
        function()
          require("neo-tree.command").execute({ toggle = false, dir = LazyVim.root() })
        end,
        desc = "Explorer NeoTree (Root Dir)",
        remap = true,
      },
      {
        "<leader>E",
        function()
          require("neo-tree.command").execute({ toggle = false, dir = vim.uv.cwd() })
        end,
        desc = "Explorer NeoTree (cwd)",
        remap = true,
      },
    },
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
