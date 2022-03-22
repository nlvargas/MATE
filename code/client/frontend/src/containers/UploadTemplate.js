import React, { useState } from 'react';
import axios from 'axios';
import style from './styles';
import regeneratorRuntime from "regenerator-runtime";


export default function CreateGroupsForm(props) {
  const { step, setStep, setOptions, setStudents, attributes, modules, preferencesNumber,
  } = props;
  const [selectedFile, setSelectedFile] = useState(null);
  const [nextDisabled, setNextDisabled] = useState(true);
  const [uploadDisabled, setUploadDisabled] = useState(false);

  
  function onFileChange(event) {
    setSelectedFile(event.target.files[0]); 
  }

  async function onFileUpload() { 
    const formData = new FormData();
    formData.append("attributes", attributes); 
    formData.append("modules", modules);
    formData.append("preferencesNumber", preferencesNumber);
    formData.append("file", selectedFile, selectedFile.name); 
    setUploadDisabled(true);
    try {
      let response = await axios.post("/dev/upload/", formData)
      alert("Su plantilla ha sido cargada correctamente");
      setOptions(JSON.parse(response.data.a));
      setStudents(JSON.parse(response.data.students))
      setNextDisabled(false);
      setStep(step + 1);
    } catch(err) {
      alert("Ha ocurrido un error. Por favor inténtelo de nuevo");
      console.log("Error fetching data-----------", err);
    }
    setUploadDisabled(false);
  }; 
   
  return (
      <div>
        <div style={style.cont}>
          <h3> Subir template </h3>
          <input type="file" onChange={onFileChange}/>
          <button disabled={uploadDisabled} onClick={() => onFileUpload()}>Subir</button>
        </div>
        <p></p>
        <button onClick={() => setStep(step - 1)}> Atras </button>
        <button disabled={nextDisabled} onClick={() => setStep(step + 1)}> Siguiente </button>
      </div>
    );
};
