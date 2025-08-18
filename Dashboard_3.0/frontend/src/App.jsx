import React, { useState, useEffect } from "react";
import Splash from "./components/Splash";
import HeliosDashboard from "./modules/cie/HeliosDashboard";
import FSSDashboard from "./modules/fss/FSSDashboard";
import ShutdownComplete from "./components/ShutdownComplete";
import ContactsPage from "./pages/ContactsPage";

export default function App() {
const [view, setView] = useState("splash");             // splash, dashboard, shutdown
const [activeModule, setActiveModule] = useState("cie"); // cie | fss | contacts

  // ⏱ Ensure splash stays up for minimum 2s
  useEffect(() => {
    const timer = setTimeout(() => {
      if (view === "splash") {
        setView("dashboard");
      }
    }, 2000);
    return () => clearTimeout(timer);
  }, [view]);

  const renderDashboard = () => {
    const sharedProps = {
      onReady: () => {
        console.log(`✅ ${activeModule.toUpperCase()} dashboard ready`);
        setView("dashboard");
      },
      onShutdown: () => setView("shutdown"),
    };

if (activeModule === "cie") return <HeliosDashboard {...sharedProps} />;
if (activeModule === "fss") return <FSSDashboard {...sharedProps} />;
if (activeModule === "contacts") return <ContactsPage />;
    return null;
  };

  return (
    <>
      {view === "splash" && <Splash />}

       {view === "dashboard" && (
         <>
           <div className="p-2 bg-gray-200 flex gap-4">
             <button
               onClick={() => setActiveModule("cie")}
               className={activeModule === "cie" ? "font-bold" : ""}
             >
               🧠 CIE
             </button>
             <button
               onClick={() => setActiveModule("fss")}
               className={activeModule === "fss" ? "font-bold" : ""}
             >
               💸 FSS
             </button>
              <button
              onClick={() => setActiveModule("contacts")}
              className={activeModule === "contacts" ? "font-bold" : ""}
            >
              👥 Contacts
            </button>
           </div>
           {renderDashboard()}
         </>
       )}

       {view === "shutdown" && <ShutdownComplete />}
     </>
   );
 }