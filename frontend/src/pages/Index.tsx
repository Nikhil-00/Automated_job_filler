import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import Navbar from "@/components/Navbar";
import AnimatedBackground from "@/components/AnimatedBackground";
import StepOnboarding from "@/components/StepOnboarding";
import StepProfile from "@/components/StepProfile";
import StepPlatform from "@/components/StepPlatform";
import { CvExtractedData, ProfileData } from "@/lib/mockApi";

const Index = () => {
  const [step, setStep]             = useState(0);
  const [extractedData, setExtracted] = useState<CvExtractedData | null>(null);
  const [isExtracting, setExtracting] = useState(false);
  const [onboardingData, setOnboarding] = useState<{ firstName: string; lastName: string; phone: string; email: string } | null>(null);
  const [profileData, setProfileData]   = useState<ProfileData | null>(null);

  return (
    <div className="min-h-screen">
      <AnimatedBackground />
      <Navbar currentStep={step} />

      <main className="pt-20 pb-12 px-4 sm:px-6">
        <AnimatePresence mode="wait">
          {step === 0 && (
            <StepOnboarding
              key="step0"
              onNext={(data) => {
                setOnboarding({ firstName: data.firstName, lastName: data.lastName, phone: data.phone, email: data.email });
                setExtracting(true);
                // Resolve in background — StepProfile will receive data when ready
                data.extractionPromise
                  .then(setExtracted)
                  .catch(console.error)
                  .finally(() => setExtracting(false));
                setStep(1);
              }}
            />
          )}
          {step === 1 && (
            <StepProfile
              key="step1"
              extractedData={extractedData}
              isExtracting={isExtracting}
              onNext={(p) => {
                setProfileData({
                  firstName:    onboardingData?.firstName ?? "",
                  lastName:     onboardingData?.lastName  ?? "",
                  phone:        onboardingData?.phone     ?? "",
                  email:        onboardingData?.email     ?? "",
                  currentCtc:   p.currentCtc,
                  expectedCtc:  p.expectedCtc,
                  location:     p.location,
                  jobTitle:     p.jobTitle,
                  noticePeriod: p.noticePeriod,
                  experience:   p.experience,
                  linkedin:     p.linkedin,
                  github:       p.github,
                });
                setStep(2);
              }}
            />
          )}
          {step === 2 && profileData && (
            <StepPlatform key="step2" profileData={profileData} />
          )}
        </AnimatePresence>
      </main>
    </div>
  );
};

export default Index;
