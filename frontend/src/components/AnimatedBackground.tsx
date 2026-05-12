const AnimatedBackground = () => (
  <div className="fixed inset-0 -z-10 overflow-hidden">
    <div className="absolute inset-0 bg-background" />
    <div
      className="absolute top-[-15%] right-[-10%] w-[45%] h-[45%] rounded-full opacity-[0.08] blur-[160px]"
      style={{ background: "hsl(221 83% 53%)" }}
    />
    <div
      className="absolute bottom-[-10%] left-[-5%] w-[35%] h-[35%] rounded-full opacity-[0.05] blur-[160px]"
      style={{ background: "hsl(225 68% 43%)" }}
    />
  </div>
);

export default AnimatedBackground;
