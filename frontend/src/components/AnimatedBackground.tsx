const AnimatedBackground = () => (
  <div className="fixed inset-0 -z-10 overflow-hidden">
    <div className="absolute inset-0 bg-background" />
    <div
      className="absolute top-[-30%] left-[-20%] w-[70%] h-[70%] rounded-full opacity-20 blur-[120px] animate-gradient"
      style={{ background: "linear-gradient(135deg, hsl(217 91% 60%), hsl(270 70% 60%))" }}
    />
    <div
      className="absolute bottom-[-20%] right-[-20%] w-[60%] h-[60%] rounded-full opacity-15 blur-[120px] animate-gradient"
      style={{ background: "linear-gradient(225deg, hsl(270 70% 60%), hsl(217 91% 60%))", animationDelay: "3s" }}
    />
  </div>
);

export default AnimatedBackground;
