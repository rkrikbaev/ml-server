
from pprint import pformat
from pathlib import Path


class ModelWithMetaInfo:
    def __init__(self, model_params, verbose, debug):
        self.model = None
        self.model_params = model_params
        self.verbose = verbose
        self.debug = debug

    def save_model(self, filepath: Path):
        """Save model and meta info to filepath."""
        raise NotImplementedError("Saving should be implemented in the subclass.")

    @staticmethod
    def load_model(filepath: Path):
        """Load model and meta info from filepath."""
        raise NotImplementedError("Loading should be implemented in the subclass.")
    
    def predict(self, df):
        """Predict values for df."""
        raise NotImplementedError("Prediction s.")
    
    def fit(self, df_train, df_val):
        """Train model."""
        raise NotImplementedError("Training is not implemented in this snippet.")
    
    def __repr__(self):
        args = self.__dict__
        representation = pformat(args)
        return 'ModelWithMetaInfo(' + representation + ')'
