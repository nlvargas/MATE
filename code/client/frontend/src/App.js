import React, { useState } from 'react';
import { render } from "react-dom";

import CreateTemplate from './containers/CreateTemplate';
import UploadTemplate from './containers/UploadTemplate';
import CreateGroups from './containers/CreateGroups';


function WizardForm(props) {
  const [attributes, setAttributes] = useState([]);
  const [preferences, setPreferences] = useState([]);
  const [modules, setModules] = useState([]);
  const [options, setOptions] = useState({});
  const [preferencesNumber, setPreferencesNumber] = useState(0);
  const [students, setStudents] = useState([]);
  const [step, setStep] = useState(1);

  function wizard() {
    switch (step) {
      case 1: return <CreateTemplate step={step} 
                                     setStep={setStep} 
                                     attributes={attributes} 
                                     setAttributes={setAttributes}
                                     preferences={preferences} 
                                     setPreferences={setPreferences}
                                     preferencesNumber={preferencesNumber} 
                                     setPreferencesNumber={setPreferencesNumber}
                                     modules={modules} 
                                     setModules={setModules} />
                                     
      case 2: return <UploadTemplate step={step} 
                                     setStep={setStep} 
                                     attributes={attributes}
                                     preferences={preferences} 
                                     modules={modules}
                                     preferencesNumber={preferencesNumber} 
                                     setOptions={setOptions}
                                     setStudents={setStudents} />

      case 3: return <CreateGroups step={step} 
                                   setStep={setStep}
                                   attributes={attributes} 
                                   preferences={preferences} 
                                   preferencesNumber={preferencesNumber}
                                   modules={modules}
                                   options={options} 
                                   students={students} />

      default: return null
    }
  }
  return (
    <div>
      {wizard()}
    </div>
  );
}



export default function App() {
  return <WizardForm/>;
};


const container = document.getElementById("app");
render(<App/> ,container);