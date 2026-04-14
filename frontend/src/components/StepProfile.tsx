import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import GlowButton from "./GlowButton";
import { CvExtractedData } from "@/lib/mockApi";

interface StepProfileProps {
  extractedData: CvExtractedData | null;
  isExtracting:  boolean;
  onNext: (profileData: Record<string, any>) => void;
}

const noticePeriods = ["Immediate", "15 days", "30 days", "60 days", "90 days"];

const StepProfile = ({ extractedData, isExtracting, onNext }: StepProfileProps) => {
  const [currentCtc, setCurrentCtc] = useState("");
  const [expectedCtc, setExpectedCtc] = useState("");
  const [location, setLocation] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [noticePeriod, setNoticePeriod] = useState("30 days");
  const [experience, setExperience] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [github, setGithub] = useState("");

  // When extraction finishes in background, auto-fill the AI fields
  useEffect(() => {
    if (extractedData) {
      if (!jobTitle)    setJobTitle(extractedData.jobTitle);
      if (!experience)  setExperience(String(extractedData.yearsOfExperience));
    }
  }, [extractedData]);

  const canContinue = currentCtc && expectedCtc && location && jobTitle && experience;

  const inputCls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition";

  return (
    <motion.div
      initial={{ opacity: 0, x: 80 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -80 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-xl mx-auto"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="glass-card p-6 sm:p-8 glow-purple"
      >
        <h2 className="text-2xl font-bold text-gradient mb-2">Complete Your Profile</h2>
        <p className="text-muted-foreground text-sm mb-6">We pre-filled some details from your CV. Review and complete the rest.</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-muted-foreground mb-1">Current CTC (₹/year)</label>
            <input type="number" value={currentCtc} onChange={(e) => setCurrentCtc(e.target.value)} className={inputCls} placeholder="800000" />
          </div>
          <div>
            <label className="block text-sm text-muted-foreground mb-1">Expected CTC (₹/year)</label>
            <input type="number" value={expectedCtc} onChange={(e) => setExpectedCtc(e.target.value)} className={inputCls} placeholder="1200000" />
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm text-muted-foreground mb-1">Current Location</label>
          <input value={location} onChange={(e) => setLocation(e.target.value)} className={inputCls} placeholder="Bangalore, India" />
        </div>

        <div className="mb-4">
          <label className="block text-sm text-muted-foreground mb-1">
            Current Job Title
            <span className="text-primary text-xs ml-1">(from CV)</span>
            {isExtracting && !extractedData && (
              <span className="inline-flex items-center gap-1 text-xs text-primary/60 ml-2">
                <Loader2 className="w-3 h-3 animate-spin" /> AI reading CV...
              </span>
            )}
          </label>
          {isExtracting && !extractedData ? (
            <div className="w-full h-10 rounded-lg bg-muted animate-pulse" />
          ) : (
            <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} className={inputCls} placeholder="e.g. Data Scientist" />
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-muted-foreground mb-1">Notice Period</label>
            <select value={noticePeriod} onChange={(e) => setNoticePeriod(e.target.value)} className={inputCls}>
              {noticePeriods.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-muted-foreground mb-1">
              Years of Experience
              {isExtracting && !extractedData && (
                <span className="inline-flex items-center gap-1 text-xs text-primary/60 ml-2">
                  <Loader2 className="w-3 h-3 animate-spin" />
                </span>
              )}
            </label>
            {isExtracting && !extractedData ? (
              <div className="w-full h-10 rounded-lg bg-muted animate-pulse" />
            ) : (
              <input type="number" value={experience} onChange={(e) => setExperience(e.target.value)} className={inputCls} placeholder="e.g. 2" />
            )}
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm text-muted-foreground mb-1">LinkedIn URL <span className="text-muted-foreground/50 text-xs">(optional)</span></label>
          <input value={linkedin} onChange={(e) => setLinkedin(e.target.value)} className={inputCls} placeholder="https://linkedin.com/in/..." />
        </div>

        <div className="mb-6">
          <label className="block text-sm text-muted-foreground mb-1">GitHub URL <span className="text-muted-foreground/50 text-xs">(optional)</span></label>
          <input value={github} onChange={(e) => setGithub(e.target.value)} className={inputCls} placeholder="https://github.com/..." />
        </div>

        <GlowButton
          disabled={!canContinue}
          onClick={() => onNext({ currentCtc, expectedCtc, location, jobTitle, noticePeriod, experience, linkedin, github })}
          className="w-full"
        >
          Save & Continue →
        </GlowButton>
      </motion.div>
    </motion.div>
  );
};

export default StepProfile;
