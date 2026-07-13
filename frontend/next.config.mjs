import { fileURLToPath } from 'url'

/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // 固定 workspace root 為本專案資料夾，避免 Next.js 誤抓到使用者家目錄下
  // 其他專案殘留的 package-lock.json 而顯示多重 lockfile 警告。
  outputFileTracingRoot: fileURLToPath(new URL('.', import.meta.url)),
}

export default nextConfig
