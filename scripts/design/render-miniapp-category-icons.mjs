/**
 * 将 8 个首页一级分类的专属彩色 SVG 矢量源文件同源渲染为 160x160 高清透明 PNG。
 * 渲染工具由运行参数 --sharp-root 或工作区依赖提供，不向小程序或后端引入前端图像构建依赖。
 */
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { lstat, mkdir, mkdtemp, readFile, rename, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const { values } = parseArgs({
  options: {
    'sharp-root': { type: 'string' },
    check: { type: 'boolean', default: false },
  },
})

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const appDir = join(root, 'apps/miniapp')
const dataPath = join(root, 'apps/backend/scripts/data/home_categories.v1.json')
const outputDir = join(root, 'apps/backend/scripts/data/category_icons')

const requireFromApp = createRequire(join(appDir, 'package.json'))
const sharpPath = values['sharp-root']
  ? requireFromApp.resolve('sharp', { paths: [resolve(values['sharp-root'])] })
  : requireFromApp.resolve('sharp')
const sharp = requireFromApp(sharpPath)

/**
 * 统一生成 160x160 彩色圆润底座与主体投影层。
 */
function buildBadgeSvg(slug, colors, bodyContent) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">
  <defs>
    <linearGradient id="${slug}-bg" x1="20%" y1="8%" x2="82%" y2="94%">
      <stop offset="0%" stop-color="${colors.top}" />
      <stop offset="100%" stop-color="${colors.bottom}" />
    </linearGradient>
    <radialGradient id="${slug}-glow" cx="35%" cy="28%" r="60%">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.34" />
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0" />
    </radialGradient>
    ${colors.defs ?? ''}
  </defs>
  <ellipse cx="80" cy="146" rx="46" ry="7" fill="${colors.shadow}" opacity="0.20" />
  <circle cx="80" cy="86" r="57" fill="url(#${slug}-bg)" />
  <circle cx="80" cy="86" r="57" fill="url(#${slug}-glow)" />
  <circle cx="80" cy="86" r="55" fill="none" stroke="#FFFFFF" stroke-opacity="0.38" stroke-width="2" />
  <ellipse cx="80" cy="123" rx="35" ry="7.5" fill="${colors.shadow}" opacity="0.22" />
  <g transform="translate(0 -6)">
  ${bodyContent}
  </g>
</svg>
`
}

// 8 个一级分类对应的彩色矢量图标定义，风格统一为柔彩渐变底盘 + 立体具象彩图
const CATEGORY_SVGS = {
  // 1. 生鲜粮油：粮油、果蔬、农产品（翠绿底座 + 金黄麦穗 + 立体胡萝卜 + 红润番茄）
  'fresh-grain': buildBadgeSvg(
    'fresh-grain',
    {
      top: '#9CEB5A',
      bottom: '#39B524',
      shadow: '#19660E',
      defs: `<linearGradient id="fg-grain" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#FFE76E" />
        <stop offset="100%" stop-color="#F59E0B" />
      </linearGradient>
      <linearGradient id="fg-carrot" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#FFA53B" />
        <stop offset="100%" stop-color="#EE4B14" />
      </linearGradient>
      <linearGradient id="fg-leaf" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#7BF154" />
        <stop offset="100%" stop-color="#17872B" />
      </linearGradient>
      <linearGradient id="fg-tomato" x1="20%" y1="10%" x2="85%" y2="95%">
        <stop offset="0%" stop-color="#FF7868" />
        <stop offset="100%" stop-color="#D92121" />
      </linearGradient>`,
    },
    `<g transform="translate(52 72) rotate(-18)">
      <path d="M0 44 C-2 22 0 4 4 -16" fill="none" stroke="#FDE047" stroke-width="3.5" stroke-linecap="round" />
      <ellipse cx="-8" cy="24" rx="5.5" ry="9" transform="rotate(-32 -8 24)" fill="url(#fg-grain)" />
      <ellipse cx="9" cy="22" rx="5.5" ry="9" transform="rotate(32 9 22)" fill="url(#fg-grain)" />
      <ellipse cx="-7" cy="9" rx="5.5" ry="9" transform="rotate(-28 -7 9)" fill="url(#fg-grain)" />
      <ellipse cx="9" cy="7" rx="5.5" ry="9" transform="rotate(28 9 7)" fill="url(#fg-grain)" />
      <ellipse cx="-5" cy="-6" rx="5" ry="8.5" transform="rotate(-24 -5 -6)" fill="url(#fg-grain)" />
      <ellipse cx="9" cy="-8" rx="5" ry="8.5" transform="rotate(24 9 -8)" fill="url(#fg-grain)" />
      <ellipse cx="3" cy="-20" rx="5" ry="9" fill="#FFF08A" />
    </g>
    <g transform="translate(95 79) rotate(22)">
      <path d="M-2 -34 C-14 -50 -2 -58 2 -40 C6 -58 18 -50 6 -34 Z" fill="url(#fg-leaf)" />
      <path d="M-14 -26 C-28 -36 -22 -48 -6 -32 Z" fill="url(#fg-leaf)" />
      <path d="M16 -26 C30 -36 24 -48 8 -32 Z" fill="url(#fg-leaf)" />
      <path d="M-20 -18 C-21 -30 -10 -36 2 -36 C14 -36 24 -30 23 -18 C21 4 10 38 1 42 C-8 38 -19 4 -20 -18 Z" fill="url(#fg-carrot)" />
      <path d="M-12 -18 C-12 -25 -6 -29 0 -29" fill="none" stroke="#FFFFFF" stroke-opacity="0.65" stroke-width="4" stroke-linecap="round" />
      <path d="M-13 -4 L-3 -4 M5 8 L15 8 M-10 18 L-2 18" fill="none" stroke="#C2380C" stroke-opacity="0.45" stroke-width="3" stroke-linecap="round" />
    </g>
    <circle cx="56" cy="107" r="17.5" fill="url(#fg-tomato)" />
    <ellipse cx="50" cy="100" rx="5.5" ry="3.5" transform="rotate(-28 50 100)" fill="#FFFFFF" opacity="0.55" />
    <path d="M56 89 C52 84 48 87 52 91 C56 93 60 93 62 89 C60 85 57 86 56 89 Z" fill="#22A138" />`,
  ),

  // 2. 餐饮烘焙：美食、蛋糕、快餐（暖阳金黄底座 + 奶油草莓蛋糕 + 餐叉）
  'dining-bakery': buildBadgeSvg(
    'dining-bakery',
    {
      top: '#FFE66B',
      bottom: '#F49D12',
      shadow: '#A15C04',
      defs: `<linearGradient id="db-sponge" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#FCD282" />
        <stop offset="100%" stop-color="#E57B20" />
      </linearGradient>
      <linearGradient id="db-cream" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#FFFFFF" />
        <stop offset="100%" stop-color="#FFE6EE" />
      </linearGradient>
      <linearGradient id="db-berry" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#FF597C" />
        <stop offset="100%" stop-color="#D41B40" />
      </linearGradient>
      <linearGradient id="db-fork" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#E2E8F0" />
        <stop offset="100%" stop-color="#94A3B8" />
      </linearGradient>`,
    },
    `<g transform="translate(49 87) rotate(-18)">
      <rect x="-5" y="-6" width="10" height="42" rx="5" fill="#FF6647" />
      <rect x="-2.5" y="-22" width="5" height="20" rx="2.5" fill="url(#db-fork)" />
      <path d="M-10 -38 L-10 -24 C-10 -18 -5 -16 0 -16 C5 -16 10 -18 10 -24 L10 -38" fill="none" stroke="url(#db-fork)" stroke-width="4" stroke-linecap="round" />
      <path d="M-3.5 -38 L-3.5 -22 M3.5 -38 L3.5 -22" fill="none" stroke="url(#db-fork)" stroke-width="3.4" stroke-linecap="round" />
    </g>
    <ellipse cx="90" cy="122" rx="37" ry="9" fill="#FFFDF7" />
    <ellipse cx="90" cy="120" rx="34" ry="7" fill="#FFE6B8" />
    <rect x="60" y="74" width="60" height="44" rx="12" fill="url(#db-sponge)" />
    <path d="M60 95 Q70 101 80 95 T100 95 T120 95 L120 101 Q110 107 100 101 T80 101 T60 101 Z" fill="#FF6B8B" />
    <path d="M58 76 C58 63 68 58 90 58 C112 58 122 63 122 76 C122 83 118 89 113 89 C108 89 107 82 102 82 C96 82 95 92 89 92 C83 92 82 81 76 81 C71 81 70 88 65 88 C60 88 58 83 58 76 Z" fill="url(#db-cream)" />
    <path d="M76 50 C76 40 83 32 90 32 C97 32 104 40 104 50 C104 60 96 66 90 66 C84 66 76 60 76 50 Z" fill="url(#db-berry)" />
    <path d="M81 33 C85 27 95 27 99 33 C94 35 86 35 81 33 Z" fill="#27AE49" />
    <ellipse cx="84" cy="44" rx="3.2" ry="5" transform="rotate(-20 84 44)" fill="#FFFFFF" opacity="0.55" />
    <circle cx="94" cy="47" r="1.4" fill="#FFE484" />
    <circle cx="88" cy="55" r="1.4" fill="#FFE484" />
    <circle cx="96" cy="56" r="1.4" fill="#FFE484" />`,
  ),

  // 3. 家居日化：日用品、清洁、百货（晴空蓝底座 + 洗护按压瓶 + 清洁护理罐 + 泡泡星芒）
  'home-daily': buildBadgeSvg(
    'home-daily',
    {
      top: '#6BCEFF',
      bottom: '#188CE0',
      shadow: '#0D5091',
      defs: `<linearGradient id="hd-bottle" x1="15%" y1="0%" x2="90%" y2="100%">
        <stop offset="0%" stop-color="#FFFFFF" />
        <stop offset="100%" stop-color="#D6ECFF" />
      </linearGradient>
      <linearGradient id="hd-pump" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#FFE059" />
        <stop offset="100%" stop-color="#F5940A" />
      </linearGradient>
      <linearGradient id="hd-jar" x1="15%" y1="0%" x2="85%" y2="100%">
        <stop offset="0%" stop-color="#76ECC7" />
        <stop offset="100%" stop-color="#14A885" />
      </linearGradient>`,
    },
    `<rect x="61" y="42" width="16" height="14" rx="4" fill="url(#hd-pump)" />
    <path d="M54 34 L86 34 C90 34 93 36 93 40 L93 42 L62 42 L62 40 L54 40 Z" fill="url(#hd-pump)" />
    <rect x="46" y="54" width="46" height="66" rx="16" fill="url(#hd-bottle)" />
    <rect x="46" y="76" width="46" height="24" fill="#FF8C42" />
    <path d="M69 81 C65 86 63 89 63 92 A6 6 0 0 0 75 92 C75 89 73 86 69 81 Z" fill="#FFFFFF" opacity="0.92" />
    <rect x="52" y="61" width="6" height="44" rx="3" fill="#FFFFFF" opacity="0.7" />
    <rect x="86" y="82" width="38" height="38" rx="11" fill="url(#hd-jar)" />
    <rect x="84" y="75" width="42" height="11" rx="5.5" fill="#FFFFFF" stroke="#CBE5FA" stroke-width="1.4" />
    <ellipse cx="98" cy="100" rx="5" ry="8" fill="#FFFFFF" opacity="0.28" />
    <circle cx="114" cy="54" r="9" fill="#FFFFFF" fill-opacity="0.35" stroke="#FFFFFF" stroke-width="1.8" />
    <circle cx="111" cy="51" r="2.2" fill="#FFFFFF" opacity="0.8" />
    <circle cx="122" cy="68" r="5" fill="#FFFFFF" fill-opacity="0.35" stroke="#FFFFFF" stroke-width="1.5" />
    <path d="M40 44 L43 51 L50 54 L43 57 L40 64 L37 57 L30 54 L37 51 Z" fill="#FFF59D" />`,
  ),

  // 4. 母婴亲子：婴儿、母婴、亲子（樱花粉底座 + 宽口婴儿奶瓶 + 奶嘴与爱心 + 小星星）
  'mother-baby': buildBadgeSvg(
    'mother-baby',
    {
      top: '#FFA8C3',
      bottom: '#F04E7C',
      shadow: '#9E1F47',
      defs: `<linearGradient id="mb-bottle" x1="15%" y1="0%" x2="85%" y2="100%">
        <stop offset="0%" stop-color="#FFFFFF" />
        <stop offset="100%" stop-color="#FFEFF4" />
      </linearGradient>
      <linearGradient id="mb-milk" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#FFECC2" />
        <stop offset="100%" stop-color="#FFD07B" />
      </linearGradient>
      <linearGradient id="mb-cap" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#6DD0FF" />
        <stop offset="100%" stop-color="#228CE6" />
      </linearGradient>
      <linearGradient id="mb-nipple" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#FFE09C" />
        <stop offset="100%" stop-color="#F59B38" />
      </linearGradient>`,
    },
    `<g transform="translate(76 80) rotate(-18)">
      <path d="M-8 -44 C-8 -54 8 -54 8 -44 L11 -32 L-11 -32 Z" fill="url(#mb-nipple)" />
      <circle cx="0" cy="-50" r="7" fill="url(#mb-nipple)" />
      <rect x="-22" y="-33" width="44" height="14" rx="7" fill="url(#mb-cap)" />
      <rect x="-20" y="-20" width="40" height="62" rx="14" fill="url(#mb-bottle)" />
      <path d="M-17 0 Q0 -4 17 0 L17 28 C17 35 12 39 5 39 L-5 39 C-12 39 -17 35 -17 28 Z" fill="url(#mb-milk)" />
      <path d="M-16 -6 L-8 -6 M-16 4 L-6 4 M-16 14 L-8 14 M-16 24 L-6 24" fill="none" stroke="#85C7FF" stroke-width="2.6" stroke-linecap="round" />
      <path d="M4 12 C4 8 9 7 11 10 C13 7 18 8 18 12 C18 17 11 22 11 22 C11 22 4 17 4 12 Z" fill="#FF5A82" />
      <rect x="-12" y="-13" width="5" height="40" rx="2.5" fill="#FFFFFF" opacity="0.7" />
    </g>
    <path d="M114 88 L118 96 L127 97 L120 103 L122 112 L114 107 L106 112 L108 103 L101 97 L110 96 Z" fill="#FFE666" stroke="#FFFFFF" stroke-width="1.5" stroke-linejoin="round" />
    <circle cx="44" cy="48" r="5" fill="#FFFFFF" opacity="0.7" />`,
  ),

  // 5. 宠物生活：小狗、宠物、猫粮狗粮（琥珀暖橙底座 + Q 版萌宠小狗 + 肉垫爪印）
  'pet-life': buildBadgeSvg(
    'pet-life',
    {
      top: '#FFD266',
      bottom: '#F58220',
      shadow: '#9E4505',
      defs: `<linearGradient id="pl-fur" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#F7AC54" />
        <stop offset="100%" stop-color="#D46F1E" />
      </linearGradient>
      <linearGradient id="pl-ear" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#B85614" />
        <stop offset="100%" stop-color="#873A08" />
      </linearGradient>
      <linearGradient id="pl-paw" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#FF9BB0" />
        <stop offset="100%" stop-color="#EE4B71" />
      </linearGradient>`,
    },
    `<ellipse cx="44" cy="76" rx="12" ry="20" transform="rotate(24 44 76)" fill="url(#pl-ear)" />
    <ellipse cx="106" cy="76" rx="12" ry="20" transform="rotate(-24 106 76)" fill="url(#pl-ear)" />
    <rect x="44" y="42" width="62" height="60" rx="29" fill="url(#pl-fur)" />
    <ellipse cx="75" cy="84" rx="22" ry="17" fill="#FFF7EB" />
    <circle cx="62" cy="68" r="5" fill="#2A1B12" />
    <circle cx="88" cy="68" r="5" fill="#2A1B12" />
    <circle cx="60.5" cy="66" r="1.8" fill="#FFFFFF" />
    <circle cx="86.5" cy="66" r="1.8" fill="#FFFFFF" />
    <ellipse cx="75" cy="79" rx="6.5" ry="4.5" fill="#3B2314" />
    <path d="M68 87 Q71.5 92 75 86 Q78.5 92 82 87" fill="none" stroke="#593520" stroke-width="2.5" stroke-linecap="round" />
    <path d="M71 89 L79 89 L79 94 A4 4 0 0 1 71 94 Z" fill="#FF6B8B" />
    <g transform="translate(110 105) rotate(-12)">
      <circle cx="0" cy="4" r="14" fill="#FFFFFF" />
      <ellipse cx="0" cy="7" rx="8.5" ry="7" fill="url(#pl-paw)" />
      <circle cx="-8.5" cy="-2.5" r="3.4" fill="url(#pl-paw)" />
      <circle cx="0" cy="-6" r="3.6" fill="url(#pl-paw)" />
      <circle cx="8.5" cy="-2.5" r="3.4" fill="url(#pl-paw)" />
    </g>`,
  ),

  // 6. 名烟名酒：礼盒、酒水（鎏金绯红底座 + 红金蝴蝶结礼盒 + 红酒杯）
  'fine-tobacco-wine': buildBadgeSvg(
    'fine-tobacco-wine',
    {
      top: '#FF7969',
      bottom: '#D12622',
      shadow: '#7D100D',
      defs: `<linearGradient id="ftw-box" x1="10%" y1="0%" x2="90%" y2="100%">
        <stop offset="0%" stop-color="#D92638" />
        <stop offset="100%" stop-color="#870D19" />
      </linearGradient>
      <linearGradient id="ftw-gold" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#FFF08A" />
        <stop offset="100%" stop-color="#E59300" />
      </linearGradient>
      <linearGradient id="ftw-wine" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#E11D48" />
        <stop offset="100%" stop-color="#700926" />
      </linearGradient>`,
    },
    `<path d="M62 45 C52 33 44 41 54 48 L64 48 Z" fill="url(#ftw-gold)" />
    <path d="M70 45 C80 33 88 41 78 48 L68 48 Z" fill="url(#ftw-gold)" />
    <rect x="40" y="56" width="52" height="58" rx="9" fill="url(#ftw-box)" />
    <rect x="36" y="47" width="60" height="16" rx="6" fill="#E0283B" stroke="#FFD65A" stroke-opacity="0.5" stroke-width="1.2" />
    <rect x="61" y="47" width="10" height="67" fill="url(#ftw-gold)" />
    <rect x="40" y="80" width="52" height="9" fill="url(#ftw-gold)" />
    <g transform="translate(104 82)">
      <path d="M-16 -34 L16 -34 L15 -14 C14 2 -14 2 -15 -14 Z" fill="#FFFFFF" fill-opacity="0.92" stroke="#F8D8DC" stroke-width="1.5" />
      <path d="M-13 -19 Q0 -16 13 -19 L13 -14 C12 -1 -12 -1 -13 -14 Z" fill="url(#ftw-wine)" />
      <ellipse cx="0" cy="-19" rx="13" ry="3.2" fill="#FB7185" opacity="0.6" />
      <rect x="-2.2" y="-1" width="4.4" height="29" fill="#FFFFFF" opacity="0.92" />
      <ellipse cx="0" cy="29" rx="13" ry="4" fill="#FFFFFF" opacity="0.95" />
      <path d="M-9 -29 L-9 -14" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" opacity="0.7" />
    </g>`,
  ),

  // 7. 车主服务：汽车、加油、维修（科技蔚蓝底座 + 圆润红色轿车 + 加油油滴标志）
  'car-owner-service': buildBadgeSvg(
    'car-owner-service',
    {
      top: '#6EB8FF',
      bottom: '#2560E8',
      shadow: '#12338C',
      defs: `<linearGradient id="cos-car" x1="15%" y1="0%" x2="85%" y2="100%">
        <stop offset="0%" stop-color="#FF7152" />
        <stop offset="100%" stop-color="#D9251D" />
      </linearGradient>
      <linearGradient id="cos-glass" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#F0F9FF" />
        <stop offset="100%" stop-color="#7DD3FC" />
      </linearGradient>
      <linearGradient id="cos-fuel" x1="20%" y1="0%" x2="80%" y2="100%">
        <stop offset="0%" stop-color="#FFE059" />
        <stop offset="100%" stop-color="#F97316" />
      </linearGradient>`,
    },
    `<rect x="38" y="96" width="15" height="20" rx="5" fill="#1E293B" />
    <rect x="93" y="96" width="15" height="20" rx="5" fill="#1E293B" />
    <path d="M44 74 L51 54 C54 47 60 44 73 44 C86 44 92 47 95 54 L102 74 Z" fill="url(#cos-car)" />
    <path d="M51 70 L56 56 C58 52 62 50 73 50 C84 50 88 52 90 56 L95 70 Z" fill="url(#cos-glass)" />
    <path d="M60 54 L56 66 M68 54 L62 66" fill="none" stroke="#FFFFFF" stroke-opacity="0.7" stroke-width="3" stroke-linecap="round" />
    <rect x="35" y="70" width="76" height="34" rx="13" fill="url(#cos-car)" />
    <circle cx="48" cy="85" r="6.5" fill="#FEF08A" />
    <circle cx="98" cy="85" r="6.5" fill="#FEF08A" />
    <rect x="61" y="81" width="24" height="10" rx="5" fill="#1E293B" opacity="0.75" />
    <rect x="44" y="96" width="58" height="6" rx="3" fill="#FCA5A5" opacity="0.55" />
    <g transform="translate(115 56)">
      <path d="M0 -20 C-10 -6 -16 3 -16 11 A16 16 0 0 0 16 11 C16 3 10 -6 0 -20 Z" fill="url(#cos-fuel)" stroke="#FFFFFF" stroke-width="2.5" />
      <path d="M-4 9 L1 2 L0 9 L5 9 L-1 18 L0 11 Z" fill="#FFFFFF" />
    </g>`,
  ),

  // 8. 生活服务：服务、家政、扳手（薄荷青绿底座 + 暖黄工具箱 + 银白金属开口扳手）
  'life-service': buildBadgeSvg(
    'life-service',
    {
      top: '#5FE3BA',
      bottom: '#0F9D7C',
      shadow: '#085945',
      defs: `<linearGradient id="ls-box" x1="15%" y1="0%" x2="85%" y2="100%">
        <stop offset="0%" stop-color="#FFE46B" />
        <stop offset="100%" stop-color="#F2940C" />
      </linearGradient>
      <linearGradient id="ls-wrench" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#FFFFFF" />
        <stop offset="100%" stop-color="#94A3B8" />
      </linearGradient>`,
    },
    `<path d="M60 66 L60 56 C60 51 64 48 69 48 L83 48 C88 48 92 51 92 56 L92 66" fill="none" stroke="#EA7A0C" stroke-width="7" stroke-linecap="round" />
    <rect x="38" y="64" width="76" height="52" rx="12" fill="url(#ls-box)" />
    <path d="M38 82 L114 82" stroke="#D97706" stroke-opacity="0.4" stroke-width="3" />
    <rect x="68" y="76" width="16" height="12" rx="4" fill="#FFFFFF" />
    <g transform="translate(88 80) rotate(-38)">
      <path d="M-7 -12 L-7 34 A7 7 0 0 0 7 34 L7 -12 C14 -15 19 -22 19 -31 C19 -39 14 -45 8 -48 L8 -30 C8 -27 4 -25 0 -25 C-4 -25 -8 -27 -8 -30 L-8 -48 C-14 -45 -19 -39 -19 -31 C-19 -22 -14 -15 -7 -12 Z" fill="url(#ls-wrench)" stroke="#CBD5E1" stroke-width="1.6" stroke-linejoin="round" />
      <rect x="-2.5" y="-4" width="5" height="32" rx="2.5" fill="#94A3B8" opacity="0.55" />
    </g>`,
  ),
}

const manifest = JSON.parse(await readFile(dataPath, 'utf8'))
assert.equal(manifest.schema_version, 1, '分类种子配置版本必须是 1')
assert.equal(manifest.categories.length, 8, '首页一级分类必须是 8 项')
const targetSize = manifest.icon_size
assert.equal(targetSize, 160, '分类图标输出尺寸必须是 160x160')

const outputs = []
for (const item of manifest.categories) {
  assert.match(item.slug, /^[a-z0-9-]+$/, `非法的分类 slug: ${item.slug}`)
  const svg = CATEGORY_SVGS[item.slug]
  assert.ok(svg, `缺少分类图标 SVG 定义: ${item.slug}`)
  assert.match(svg, /^<svg\b/)
  assert(!/<(?:script|image|use)\b|(?:href|style)=/i.test(svg), `SVG 包含不允许的元素或属性: ${item.slug}`)

  const pngBytes = await sharp(Buffer.from(svg, 'utf8'), { density: 192 })
    .resize(targetSize, targetSize, { fit: 'contain', background: '#00000000' })
    .png({ compressionLevel: 9 })
    .toBuffer()

  const metadata = await sharp(pngBytes).metadata()
  const { channels } = await sharp(pngBytes).ensureAlpha().stats()
  assert(
    metadata.width === targetSize && metadata.height === targetSize && metadata.hasAlpha,
    `期望透明 ${targetSize}x${targetSize} PNG: ${item.slug}`,
  )
  assert(
    channels[3].min === 0 && channels[3].max > 0,
    `PNG 必须包含透明边缘与可见像素: ${item.slug}`,
  )
  assert(pngBytes.length < 50 * 1024, `分类 PNG 体积超过 50 KiB 上限: ${item.slug}`)

  outputs.push({
    slug: item.slug,
    svgPath: join(outputDir, `${item.slug}.svg`),
    svgBytes: Buffer.from(svg, 'utf8'),
    pngPath: join(outputDir, `${item.slug}.png`),
    pngBytes,
  })
}

if (values.check) {
  for (const entry of outputs) {
    const actualSvg = await readFile(entry.svgPath)
    const actualPng = await readFile(entry.pngPath)
    assert(entry.svgBytes.equals(actualSvg), `SVG 源文件发生漂移: ${entry.svgPath}`)
    assert(entry.pngBytes.equals(actualPng), `PNG 导出文件发生漂移: ${entry.pngPath}`)
  }
  console.log(`分类图标校验通过：${outputs.length} 组 SVG/PNG（${targetSize}x${targetSize}），sharp ${sharp.versions.sharp}`)
} else {
  await mkdir(outputDir, { recursive: true })
  assert(!(await lstat(outputDir)).isSymbolicLink(), '图标输出目录不能是符号链接')

  // 若已有旧产物先做临时目录备份，防止意外覆盖损坏
  const existing = []
  for (const entry of outputs) {
    for (const filePath of [entry.svgPath, entry.pngPath]) {
      try {
        const st = await lstat(filePath)
        assert(!st.isSymbolicLink(), `拒绝覆盖符号链接文件: ${filePath}`)
        existing.push({ path: filePath, bytes: await readFile(filePath) })
      } catch (error) {
        if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') continue
        throw error
      }
    }
  }
  if (existing.length > 0) {
    const backupDir = await mkdtemp(join(tmpdir(), 'pinjie-category-icons-'))
    console.log(`已备份旧图标文件到: ${backupDir}`)
    for (const item of existing) {
      const name = item.path.slice(outputDir.length + 1)
      await writeFile(join(backupDir, name), item.bytes, { flag: 'wx' })
    }
  }

  for (const entry of outputs) {
    for (const [targetPath, bytes] of [
      [entry.svgPath, entry.svgBytes],
      [entry.pngPath, entry.pngBytes],
    ]) {
      const tempPath = `${targetPath}.tmp`
      await writeFile(tempPath, bytes, { flag: 'wx' })
      await rename(tempPath, targetPath)
      assert((await readFile(targetPath)).equals(bytes), `写后复读不一致: ${targetPath}`)
    }
    const sha = createHash('sha256').update(entry.pngBytes).digest('hex').slice(0, 12)
    console.log(`${entry.slug}.png ${entry.pngBytes.length} bytes sha256=${sha}`)
  }
  console.log(`已生成 ${outputs.length} 组分类图标（${targetSize}x${targetSize}），sharp ${sharp.versions.sharp}`)
}
