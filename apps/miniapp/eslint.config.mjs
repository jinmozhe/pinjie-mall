import { pinjieConfig } from '@pinjie/eslint-config'
import hooks from 'eslint-plugin-react-hooks'

export default [
  ...pinjieConfig,
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['src/**/*.ts', 'src/**/*.tsx'],
    plugins: { 'react-hooks': hooks },
    languageOptions: { globals: { defineAppConfig: 'readonly', definePageConfig: 'readonly', AbortSignal: 'readonly', __API_BASE_URL__: 'readonly', __ASSET_BASE_URL__: 'readonly' } },
    rules: { ...hooks.configs.recommended.rules, '@typescript-eslint/no-explicit-any': 'error' },
  },
  { files: ['config/**/*.ts'], languageOptions: { globals: { process: 'readonly', __dirname: 'readonly' } } },
  { files: ['*.cjs'], languageOptions: { globals: { module: 'readonly', process: 'readonly' } } },
]
