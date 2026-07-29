import fs from "node:fs";
import postcss from "postcss";

const file = "static/styles.css";
const css = fs.readFileSync(file, "utf8");
const root = postcss.parse(css);
const selectors = new Set();
const colors = new Set();
let rules = 0;
let declarations = 0;
let mediaQueries = 0;

root.walkRules((rule) => {
  rules += 1;
  rule.selectors?.forEach((selector) => selectors.add(selector));
});

root.walkDecls((declaration) => {
  declarations += 1;
  declaration.value.match(/#[0-9a-f]{3,8}\b/gi)?.forEach((color) => {
    colors.add(color.toLowerCase());
  });
});

root.walkAtRules("media", () => {
  mediaQueries += 1;
});

console.log(`CSS compressé : ${Buffer.byteLength(css)} octets`);
console.log(`Règles : ${rules}`);
console.log(`Sélecteurs uniques : ${selectors.size}`);
console.log(`Déclarations : ${declarations}`);
console.log(`Couleurs uniques : ${colors.size}`);
console.log(`Media queries : ${mediaQueries}`);
