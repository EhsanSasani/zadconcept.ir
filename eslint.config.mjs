import globals from "globals";

const correctnessRules = {
  "constructor-super": "error",
  "for-direction": "error",
  "getter-return": "error",
  "no-async-promise-executor": "error",
  "no-constant-binary-expression": "error",
  "no-dupe-args": "error",
  "no-dupe-class-members": "error",
  "no-dupe-else-if": "error",
  "no-dupe-keys": "error",
  "no-func-assign": "error",
  "no-import-assign": "error",
  "no-loss-of-precision": "error",
  "no-new-native-nonconstructor": "error",
  "no-obj-calls": "error",
  "no-promise-executor-return": "error",
  "no-redeclare": "error",
  "no-self-assign": "error",
  "no-setter-return": "error",
  "no-shadow-restricted-names": "error",
  "no-sparse-arrays": "error",
  "no-this-before-super": "error",
  "no-undef": "error",
  "no-unexpected-multiline": "error",
  "no-unreachable": "error",
  "no-unreachable-loop": "error",
  "no-unused-private-class-members": "error",
  "no-unused-vars": ["error", { "argsIgnorePattern": "^_" }],
  "no-useless-assignment": "error",
  "no-useless-backreference": "error",
  "no-useless-catch": "error",
  "no-useless-escape": "error",
  "no-with": "error",
  "require-yield": "error",
  "use-isnan": "error",
  "valid-typeof": "error",
};

export default [
  {
    files: ["main/static/main/js/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: globals.browser,
    },
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
    rules: correctnessRules,
  },
  {
    files: ["tests/js/**/*.mjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.node,
        ...globals.browser,
      },
    },
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
    rules: correctnessRules,
  },
];
