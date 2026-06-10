/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ── Brand: Hi-Vis Amber (safety vests/helmets) ──
        // Unique vs competitors (Intenseye/Protex/Voxel all use blue/teal)
        brand: {
          50:  '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',   // primary
          600: '#f97316',   // primary-hover (safety orange)
          700: '#ea580c',
          800: '#c2410c',
          900: '#9a3412',
          DEFAULT: '#f59e0b',
        },
        // ── Surfaces: deep slate ──
        surface: {
          DEFAULT: '#0f172a',   // app background
          raised:  '#1e293b',   // cards/panels
          high:    '#334155',   // hover/raised
          border:  '#334155',
        },
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)',
        'hero-glow': 'radial-gradient(ellipse at top, rgba(245,158,11,0.15), transparent 60%)',
        'grid-pattern': 'linear-gradient(rgba(245,158,11,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(245,158,11,0.04) 1px, transparent 1px)',
      },
      animation: {
        'pulse-fast': 'pulse 1s cubic-bezier(0.4,0,0.6,1) infinite',
        'float': 'float 6s ease-in-out infinite',
        'glow': 'glow 2.5s ease-in-out infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%':      { transform: 'translateY(-12px)' },
        },
        glow: {
          '0%, 100%': { opacity: '0.6' },
          '50%':      { opacity: '1' },
        },
        slideIn: {
          '0%':   { transform: 'translateX(120%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
