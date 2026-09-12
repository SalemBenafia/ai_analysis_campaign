import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Satoshi', 'Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        background: {
          DEFAULT: '#0a0f1f',
          secondary: '#0f1629',
          card: '#111827',
          hover: '#1a2235',
        },
        neon: {
          blue: '#00f0ff',
          cyan: '#00d4ff',
          purple: '#7c3aed',
          green: '#00ff88',
          pink: '#ff007f',
        },
        border: {
          DEFAULT: '#1e2d4a',
          bright: '#00f0ff33',
        },
        text: {
          primary: '#e2e8f0',
          secondary: '#94a3b8',
          muted: '#475569',
          accent: '#00f0ff',
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-cyber': 'linear-gradient(135deg, #0a0f1f 0%, #0f1629 100%)',
        'gradient-neon': 'linear-gradient(135deg, #00f0ff22, #7c3aed22)',
        'gradient-card': 'linear-gradient(145deg, #111827, #0f1629)',
      },
      boxShadow: {
        neon: '0 0 20px rgba(0, 240, 255, 0.3)',
        'neon-sm': '0 0 10px rgba(0, 240, 255, 0.2)',
        'neon-lg': '0 0 40px rgba(0, 240, 255, 0.4)',
        card: '0 4px 24px rgba(0, 0, 0, 0.4)',
      },
      animation: {
        'pulse-neon': 'pulse-neon 2s ease-in-out infinite',
        'fade-in': 'fade-in 0.3s ease-out',
        'slide-up': 'slide-up 0.4s ease-out',
        shimmer: 'shimmer 2s linear infinite',
      },
      keyframes: {
        'pulse-neon': {
          '0%, 100%': { boxShadow: '0 0 10px rgba(0,240,255,0.2)' },
          '50%': { boxShadow: '0 0 30px rgba(0,240,255,0.6)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { transform: 'translateY(12px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
      },
      borderRadius: {
        lg: '0.75rem',
        xl: '1rem',
        '2xl': '1.25rem',
      },
    },
  },
  plugins: [],
}

export default config
