/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#253E5A",
        muted: "#526A70",
        action: "#253E5A",
        "action-hover": "#172C43",
        ground: "#EDF3F2",
        danger: "#AD4237",
        "danger-dark": "#8E3028",
      },
      borderRadius: {
        card: "1.125rem",
      },
    },
  },
  plugins: [],
};
