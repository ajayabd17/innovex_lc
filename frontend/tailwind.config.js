/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        queued: '#6b7280',
        running: '#2563eb',
        succeeded: '#16a34a',
        failed: '#dc2626',
      },
      boxShadow: {
        soft: '0 6px 20px rgba(15, 23, 42, 0.08)',
      },
    },
  },
  plugins: [],
};
