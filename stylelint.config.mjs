export default {
  rules: {
    "block-no-empty": true,
    "color-no-invalid-hex": true,
    "declaration-block-no-duplicate-custom-properties": true,
    "declaration-block-no-duplicate-properties": [
      true,
      { ignore: ["consecutive-duplicates-with-different-values"] }
    ],
    "function-calc-no-unspaced-operator": true,
    "no-invalid-double-slash-comments": true,
    "property-no-unknown": true,
    "selector-pseudo-class-no-unknown": true,
    "selector-pseudo-element-no-unknown": true,
    "unit-no-unknown": true
  }
};
