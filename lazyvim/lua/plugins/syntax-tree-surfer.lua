return {
  "ziontee113/syntax-tree-surfer",
  disable = true,
  keys = {
    {
      "<C-k>",
      function()
        require("syntax-tree-surfer").move("n", true)
      end,
      desc = "STSSwapCurrentNodePrevNormal",
    },
    {
      "<C-j>",
      function()
        require("syntax-tree-surfer").move("n", false)
      end,
      desc = "STSSwapCurrentNodeNextNormal",
    },
    {
      "<C-k>",
      function()
        require("syntax-tree-surfer").surf("prev", "visual", true)
      end,
      desc = "STSSwapCurrentNodePrevVisual",
      mode = { "x" },
    },
    {
      "<C-j>",
      function()
        require("syntax-tree-surfer").surf("next", "visual", true)
      end,
      desc = "STSSwapCurrentNodeNextVisual",
      mode = { "x" },
    }
  },
}

