module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  extends: ['eslint:recommended', 'plugin:vue/vue3-essential'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  globals: {
    L: 'readonly',
  },
  rules: {
    // Vue 3 SFC style used across AeroRF: script setup without explicit imports
    // of every helper is verified by the test suite instead.
    'vue/multi-word-component-names': 'off',
    'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
  },
  overrides: [
    {
      files: ['tests/**/*.js', '*.config.js'],
      env: { node: true, browser: false },
      rules: {
        'no-undef': 'off',
      },
    },
  ],
}
