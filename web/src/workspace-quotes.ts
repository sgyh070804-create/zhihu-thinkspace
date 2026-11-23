// Public-domain originals. The edition or chapter is displayed with every quotation.
export const workspaceQuotes = [
  { text: "学而时习之，不亦说乎？", source: "《论语·学而》" },
  { text: "温故而知新，可以为师矣。", source: "《论语·为政》" },
  { text: "学而不思则罔，思而不学则殆。", source: "《论语·为政》" },
  { text: "知之为知之，不知为不知，是知也。", source: "《论语·为政》" },
  { text: "见贤思齐焉，见不贤而内自省也。", source: "《论语·里仁》" },
  { text: "知之者不如好之者，好之者不如乐之者。", source: "《论语·雍也》" },
  { text: "三人行，必有我师焉。", source: "《论语·述而》" },
  { text: "默而识之，学而不厌，诲人不倦。", source: "《论语·述而》" },
  { text: "逝者如斯夫，不舍昼夜。", source: "《论语·子罕》" },
  { text: "往者不可谏，来者犹可追。", source: "《论语·微子》" },
  { text: "尽信书，则不如无书。", source: "《孟子·尽心下》" },
  { text: "学问之道无他，求其放心而已矣。", source: "《孟子·告子上》" },
  { text: "观水有术，必观其澜。", source: "《孟子·尽心上》" },
  { text: "君子深造之以道，欲其自得之也。", source: "《孟子·离娄下》" },
  { text: "不以规矩，不能成方圆。", source: "《孟子·离娄上》" },
  { text: "知人者智，自知者明。", source: "《道德经》第三十三章" },
  { text: "胜人者有力，自胜者强。", source: "《道德经》第三十三章" },
  { text: "大直若屈，大巧若拙，大辩若讷。", source: "《道德经》第四十五章" },
  { text: "天下难事必作于易，天下大事必作于细。", source: "《道德经》第六十三章" },
  { text: "千里之行，始于足下。", source: "《道德经》第六十四章" },
  { text: "知不知，上矣；不知知，病也。", source: "《道德经》第七十一章" },
  { text: "吾生也有涯，而知也无涯。", source: "《庄子·养生主》" },
  { text: "相濡以沫，不如相忘于江湖。", source: "《庄子·大宗师》" },
  { text: "不积跬步，无以至千里。", source: "《荀子·劝学》" },
  { text: "锲而不舍，金石可镂。", source: "《荀子·劝学》" },
  { text: "学然后知不足，教然后知困。", source: "《礼记·学记》" },
  { text: "博学之，审问之，慎思之，明辨之，笃行之。", source: "《礼记·中庸》" },
  { text: "苟日新，日日新，又日新。", source: "《礼记·大学》" },
  { text: "天行健，君子以自强不息。", source: "《周易·乾·象传》" },
  { text: "地势坤，君子以厚德载物。", source: "《周易·坤·象传》" },
];

export function pickWorkspaceQuote() {
  return workspaceQuotes[Math.floor(Math.random() * workspaceQuotes.length)];
}
