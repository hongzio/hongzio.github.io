return {
  "ziontee113/syntax-tree-surfer",
  disable = true,
  keys = {
    {
      "<C-m>",
      function()
        require("syntax-tree-surfer").move("n", true)
      end,
      desc = "STSSwapCurrentNodePrevNormal",
    },
    {
      "<C-n>",
      function()
        require("syntax-tree-surfer").move("n", false)
      end,
      desc = "STSSwapCurrentNodeNextNormal",
    },
    {
      "<C-m>",
      function()
        require("syntax-tree-surfer").surf("prev", "visual", true)
      end,
      desc = "STSSwapCurrentNodePrevVisual",
      mode = { "x" },
    },
    {
      "<C-n>",
      function()
        require("syntax-tree-surfer").surf("next", "visual", true)
      end,
      desc = "STSSwapCurrentNodeNextVisual",
      mode = { "x" },
    }
  },
}

