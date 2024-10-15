return {
  "nvim-telescope/telescope.nvim",
  dependencies = {
    {
      "isak102/telescope-git-file-history.nvim",
      dependencies = {
        "nvim-lua/plenary.nvim",
        "tpope/vim-fugitive",
      },
      config = function()
        require("telescope").load_extension("git_file_history")
      end,
      keys = {
        { "<leader>gH", "<cmd>Telescope git_file_history<CR>", desc = "Git file history" },
        {
          "<leader>gD",
          function()
            if
              (vim.wo.diff == false and vim.fn.getbufvar("#", "&diff") == 0)
              and (
                not string.match(vim.fn.bufname("%"), "^fugitive:") and not string.match(vim.fn.bufname("#"), "^fugitive:")
              )
            then
              print("Not in diff view.")
              return
            end
            vim.cmd("diffoff | q | Gedit")
          end,
          desc = "Close diff view",
        },
      },
    },
  },
}
