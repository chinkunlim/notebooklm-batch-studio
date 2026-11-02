/* Gemini Notebook 學習工作室 — fictional course content for the standalone demo (docs/demo/index.html).
   Everything here is made up for illustration: two courses (BIO101 細胞與分子生物學, CHEM110 普通化學),
   lectures, quiz questions, flashcards and key points. The key-point quotes appear word for word in the
   generated lecture PDFs (scripts/build_demo.py), so the reader can highlight them. */

/** The demo courses: code, name, exam date and lectures (topic, English PDF title, quiz bank, flashcards, key points). */
const DEMO_COURSES = [
  {
    code: 'BIO101', name: '細胞與分子生物學', examInDays: 18,
    lectures: [
      {
        topic: '細胞的構造與功能', title: 'Cell Structure and Function',
        quiz: [
          ['哪一個胞器負責產生細胞大部分的 ATP？', ['粒線體', '高基氏體', '溶體', '核糖體'], 0, '粒線體透過細胞呼吸的電子傳遞鏈產生大部分 ATP。'],
          ['原核細胞和真核細胞最主要的差別是什麼？', ['原核細胞沒有細胞膜', '原核細胞沒有由膜包住的細胞核', '原核細胞不含 DNA', '原核細胞沒有核糖體'], 1, '原核細胞的 DNA 位於類核區，沒有核膜包覆。'],
          ['粗糙內質網上附著的是什麼？', ['溶體', '中心粒', '核糖體', '過氧化體'], 2, '核糖體附著使內質網看起來「粗糙」，負責合成分泌與膜蛋白。'],
          ['細胞骨架的主要功能不包括下列哪一項？', ['維持細胞形狀', '協助胞器移動', '儲存遺傳資訊', '參與細胞分裂'], 2, '遺傳資訊儲存在 DNA，細胞骨架負責結構與運輸。'],
        ],
        cards: [['粒線體', '產生 ATP 的胞器，有自己的 DNA'], ['高基氏體', '修飾、分類並包裝蛋白質'], ['溶體', '含水解酵素，分解廢物與老舊胞器'], ['核仁', '合成核糖體 RNA 的地方'], ['細胞骨架', '微管、微絲、中間絲組成的支架']],
        points: [
          { quote: 'Mitochondria produce most of the ATP a cell needs', page: 2, importance: 3, note: '粒線體是細胞的能量工廠，必考。' },
          { quote: 'Prokaryotic cells lack a membrane-bound nucleus', page: 2, importance: 3, note: '原核與真核最核心的差異。' },
          { quote: 'Ribosomes on the rough endoplasmic reticulum make secreted proteins', page: 3, importance: 2, note: '粗糙內質網與分泌蛋白的關係。' },
          { quote: 'The cytoskeleton keeps the cell in shape and moves organelles', page: 3, importance: 1, note: '細胞骨架的兩大功能。' },
        ],
      },
      {
        topic: '細胞膜與物質運輸', title: 'Membranes and Transport',
        quiz: [
          ['細胞膜的基本結構是什麼？', ['蛋白質雙層', '磷脂雙層', '纖維素層', '核酸層'], 1, '流體鑲嵌模型：磷脂雙層中鑲嵌蛋白質。'],
          ['不需要消耗能量、順著濃度梯度的運輸是？', ['主動運輸', '胞吞作用', '被動運輸', '鈉鉀幫浦'], 2, '被動運輸（擴散、促進性擴散）不需 ATP。'],
          ['鈉鉀幫浦每消耗一個 ATP，會把幾個鈉離子送出細胞？', ['1', '2', '3', '4'], 2, '送出 3 個鈉離子、帶入 2 個鉀離子。'],
          ['把細胞放入高張溶液中，細胞會？', ['吸水脹大', '失水皺縮', '沒有變化', '立刻分裂'], 1, '水往溶質濃度高的地方移動，細胞失水。'],
        ],
        cards: [['擴散', '分子由高濃度往低濃度移動'], ['滲透', '水分子透過半透膜的擴散'], ['主動運輸', '逆濃度梯度、需要 ATP'], ['胞吞作用', '細胞膜內陷把大分子包進來'], ['通道蛋白', '讓特定離子快速通過的膜蛋白']],
        points: [
          { quote: 'The plasma membrane is a fluid mosaic of lipids and proteins', page: 2, importance: 3, note: '流體鑲嵌模型。' },
          { quote: 'Passive transport moves substances down their concentration gradient', page: 2, importance: 2, note: '被動運輸不需要能量。' },
          { quote: 'The sodium-potassium pump uses ATP to move ions against their gradients', page: 3, importance: 3, note: '主動運輸的經典例子。' },
        ],
      },
      {
        topic: '細胞呼吸與能量', title: 'Cellular Respiration',
        quiz: [
          ['糖解作用發生在細胞的哪裡？', ['粒線體基質', '細胞質', '內質網', '細胞核'], 1, '糖解作用在細胞質進行，不需要氧。'],
          ['電子傳遞鏈最後的電子接受者是？', ['二氧化碳', '水', '氧氣', '葡萄糖'], 2, '氧接受電子與氫離子形成水。'],
          ['一分子葡萄糖經有氧呼吸大約可產生多少 ATP？', ['2', '4', '約 30–32', '100'], 2, '現代估計約 30–32 個 ATP。'],
          ['缺氧時肌肉細胞會進行？', ['乳酸發酵', '光合作用', '酒精發酵', '克氏循環加速'], 0, '人體肌肉在缺氧時進行乳酸發酵。'],
        ],
        cards: [['糖解作用', '葡萄糖分解成兩個丙酮酸'], ['克氏循環', '在粒線體基質產生 NADH 與 FADH2'], ['電子傳遞鏈', '在粒線體內膜，產生大部分 ATP'], ['ATP 合成酶', '利用氫離子梯度合成 ATP'], ['發酵', '無氧時再生 NAD+ 的途徑']],
        points: [
          { quote: 'Glycolysis splits glucose into two pyruvate molecules in the cytoplasm', page: 2, importance: 3, note: '糖解作用的位置與產物。' },
          { quote: 'Oxygen is the final electron acceptor of the electron transport chain', page: 3, importance: 3, note: '為什麼需要呼吸氧氣。' },
        ],
      },
      {
        topic: '光合作用', title: 'Photosynthesis',
        quiz: [
          ['光反應在葉綠體的哪裡進行？', ['基質', '類囊體膜', '外膜', '細胞壁'], 1, '光反應在類囊體膜上進行。'],
          ['卡爾文循環固定的是哪一種分子？', ['氧氣', '二氧化碳', '水', '葡萄糖'], 1, 'Rubisco 把二氧化碳固定成有機分子。'],
          ['光反應釋放的氧氣來自？', ['二氧化碳', '葡萄糖', '水', '空氣'], 2, '水的光解釋放氧氣。'],
        ],
        cards: [['葉綠素', '吸收紅光與藍光的色素'], ['類囊體', '光反應發生的膜系統'], ['卡爾文循環', '在基質中固定二氧化碳'], ['Rubisco', '地球上含量最多的酵素']],
        points: [],
        laterPoints: [
          { quote: 'The light reactions take place in the thylakoid membranes', page: 2, importance: 3, note: '光反應的位置。' },
          { quote: 'The Calvin cycle fixes carbon dioxide into sugar', page: 3, importance: 3, note: '卡爾文循環做什麼。' },
        ],
      },
      {
        topic: 'DNA 複製與修復', title: 'DNA Replication and Repair',
        quiz: [
          ['DNA 複製方式稱為？', ['保守性複製', '半保留複製', '分散式複製', '隨機複製'], 1, '每個新 DNA 保留一股舊股。'],
          ['延伸新 DNA 股的主要酵素是？', ['解旋酶', 'DNA 聚合酶', '連接酶', 'RNA 聚合酶'], 1, 'DNA 聚合酶依模板加入核苷酸。'],
          ['岡崎片段出現在哪一股？', ['領先股', '延遲股', '兩股都有', '都沒有'], 1, '延遲股以片段方式不連續合成。'],
        ],
        cards: [['解旋酶', '打開 DNA 雙股'], ['引子酶', '合成 RNA 引子'], ['DNA 連接酶', '連接岡崎片段'], ['半保留複製', '新 DNA 一股舊、一股新']],
        points: [],
        laterPoints: [
          { quote: 'DNA replication is semiconservative', page: 2, importance: 3, note: '半保留複製。' },
          { quote: 'Okazaki fragments form on the lagging strand', page: 3, importance: 2, note: '延遲股的不連續合成。' },
        ],
      },
      {
        topic: '基因表現與調控', title: 'Gene Expression and Regulation',
        quiz: [
          ['轉錄的產物是？', ['蛋白質', 'mRNA', 'DNA', '胺基酸'], 1, '轉錄以 DNA 為模板合成 RNA。'],
          ['乳糖操縱組在有乳糖時會？', ['被抑制', '被開啟', '被刪除', '被複製'], 1, '乳糖使抑制子脫落，基因被開啟。'],
        ],
        cards: [['轉錄', 'DNA → RNA'], ['轉譯', 'mRNA → 蛋白質'], ['啟動子', 'RNA 聚合酶結合的位置']],
        points: [],
        laterPoints: [
          { quote: 'Transcription copies a gene into messenger RNA', page: 2, importance: 3, note: '轉錄的定義。' },
          { quote: 'The lac operon is switched on when lactose is present', page: 3, importance: 2, note: '乳糖操縱組的調控。' },
        ],
      },
    ],
  },
  {
    code: 'CHEM110', name: '普通化學', examInDays: null,
    lectures: [
      { topic: '原子結構', title: 'Atomic Structure', quiz: [['原子核由什麼組成？', ['質子與中子', '電子與質子', '只有中子', '電子與中子'], 0, '原子核含質子與中子。']], cards: [['同位素', '質子數相同、中子數不同']], points: [] },
      { topic: '化學鍵', title: 'Chemical Bonds', quiz: [['NaCl 的鍵結是？', ['共價鍵', '離子鍵', '金屬鍵', '氫鍵'], 1, '鈉與氯以離子鍵結合。']], cards: [['共價鍵', '原子共用電子對']], points: [] },
      { topic: '化學計量', title: 'Stoichiometry', quiz: [['一莫耳約有多少粒子？', ['6.02 × 10²³', '3.14', '1000', '9.8'], 0, '亞佛加厥數。']], cards: [['莫耳', '6.02 × 10²³ 個粒子']], points: [] },
      { topic: '酸鹼平衡', title: 'Acids and Bases', quiz: [['pH 7 的溶液是？', ['酸性', '中性', '鹼性', '無法判斷'], 1, '25 °C 時 pH 7 為中性。']], cards: [['緩衝溶液', '能抵抗 pH 變化的溶液']], points: [] },
    ],
  },
];

/** Starting state so the demo looks lived-in: past quiz attempts, open mistakes, finished steps and study days. */
const DEMO_SEED = {
  attempts: [
    { course: 'BIO101', lecture: 1, variant: 'L01_quiz_1', score: 3, total: 4, daysAgo: 2 },
    { course: 'BIO101', lecture: 1, variant: 'L01_quiz_2', score: 4, total: 4, daysAgo: 1 },
    { course: 'BIO101', lecture: 2, variant: 'L02_quiz_1', score: 2, total: 4, daysAgo: 1 },
  ],
  mistakes: [
    { course: 'BIO101', lecture: 2, q: 1, selected: 0, confidence: 'sure' },
    { course: 'BIO101', lecture: 2, q: 3, selected: 0, confidence: null },
    { course: 'BIO101', lecture: 1, q: 2, selected: 3, confidence: null },
  ],
  steps: [['BIO101', 1, 'audio'], ['BIO101', 1, 'guide'], ['BIO101', 2, 'audio']],
  // study sessions per day for the last 28 days (oldest first); today is filled in by what you do
  activity: [0, 1, 2, 0, 1, 1, 0, 2, 3, 1, 0, 0, 1, 2, 2, 1, 0, 1, 3, 2, 1, 1, 0, 2, 2, 3, 1, 0],
  due: [['BIO101', 1, 0, 1], ['BIO101', 1, 2, 2], ['BIO101', 2, 0, 1], ['BIO101', 2, 3, 3], ['BIO101', 3, 1, 1]],
};
